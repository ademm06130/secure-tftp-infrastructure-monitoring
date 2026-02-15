#!/usr/bin/env python3
import subprocess
import threading
import time
import re
import os
import socket
import mysql.connector

from config import DB_CONFIG, SYSLOG_CONFIG, TFTP_CONFIG

TFTP_ROOT = TFTP_CONFIG["root_directory"]
WAIT_AFTER_CLOSE = TFTP_CONFIG["wait_after_close"]

SYSLOG_HOST = SYSLOG_CONFIG["host"]
SYSLOG_PORT = SYSLOG_CONFIG["port"]

inotify_events = []
log_requests = []
log_errors = []
pending_transfers = []

lock = threading.Lock()

def connecter_db():

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"[DB CONNECTION ERROR]  {e}")
        return None

def envoyer_syslog(message, is_error=False):
    try:
        priority = 11 if is_error else 13
        syslog_message = f"<{priority}> script_tracabilite: {message}"
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(syslog_message.encode(), (SYSLOG_HOST, SYSLOG_PORT))
        sock.close()
        print(f"[SYSLOG]  Message envoyé : {message}")
    except Exception as e:
        print(f"[SYSLOG ERROR]  {e}")

def insert_transfer_db(filename, transfer_type, status, client_ip, file_size):
    conn = connecter_db()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        sql = """
            INSERT INTO file_transfers
            (filename, client_ip, file_size, transfer_type, status)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (
            filename,
            client_ip,
            file_size,
            transfer_type,
            status
        ))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[DB] ✅ {filename} | {client_ip} | {file_size} bytes | {status}")
    except Exception as e:
        print(f"[DB ERROR] ❌ {e}")

def watch_inotify():
    cmd = [
        "inotifywait",
        "-m",
        "-e", "close_write,close_nowrite",
        "--format", "%T %f %e",
        "--timefmt", "%H:%M:%S",
        TFTP_ROOT,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    for line in proc.stdout:
        parts = line.strip().split(" ", 2)
        if len(parts) == 3:
            _, fname, event_type = parts
            with lock:
                inotify_events.append({
                    "file": fname,
                    "event": event_type
                })
            print(f"[INOTIFY] {fname} {event_type}")

def watch_logs():
    cmd = ["journalctl", "-u", "tftpd-hpa", "-f", "-n", "0", "-o", "short"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    for line in proc.stdout:
        m = re.search(
            r"in\.tftpd\[(\d+)\]:\s+"
            r"(WRQ|RRQ)\s+from\s+([\d\.]+).*filename\s+(\S+)",
            line
        )
        if m:
            pid, typ, client_ip, fname = m.groups()
            with lock:
                log_requests.append({
                    "file": fname,
                    "pid": pid,
                    "type": typ,
                    "client_ip": client_ip,
                    "pending_used": False
                })
            print(f"[LOG] {typ} {fname} FROM {client_ip} PID={pid}")
            continue

        m_refused = re.search(
            r"in\.tftpd\[(\d+)\].*read:\s+Connection refused",
            line
        )
        if m_refused:
            pid = m_refused.group(1)
            with lock:
                log_errors.append({"pid": pid, "reason": "Connection refused"})
            print(f"[LOG] ERROR - Connection refused PID={pid}")
            continue

        m_nak = re.search(
            r"in\.tftpd\[(\d+)\].*NAK",
            line
        )
        if m_nak:
            pid = m_nak.group(1)
            with lock:
                log_errors.append({"pid": pid, "reason": "NAK reçu"})
            print(f"[LOG] ERROR - NAK PID={pid}")
            continue

def correlate():
    while True:
        time.sleep(0.2)
        now = time.time()

        with lock:
            for ino in list(inotify_events):
                reqs = [
                    r for r in log_requests
                    if r["file"] == ino["file"] and not r["pending_used"]
                ]
                if not reqs:
                    continue

                req = reqs[-1]

                if (req["type"] == "WRQ" and "CLOSE_WRITE" in ino["event"]) or \
                   (req["type"] == "RRQ" and "CLOSE_NOWRITE" in ino["event"]):

                    req["pending_used"] = True

                    file_path = os.path.join(TFTP_ROOT, ino["file"])
                    file_size = os.path.getsize(file_path) if os.path.exists(file_path) else None

                    pending_transfers.append({
                        "file": ino["file"],
                        "pid": req["pid"],
                        "type": req["type"],
                        "client_ip": req["client_ip"],
                        "file_size": file_size,
                        "check_at": now + WAIT_AFTER_CLOSE
                    })

                    inotify_events.remove(ino)

            for tr in list(pending_transfers):
                if now >= tr["check_at"]:
                    error = next((e for e in log_errors if e["pid"] == tr["pid"]), None)
                    status = "failed" if error else "success"
                    db_type = "upload" if tr["type"] == "WRQ" else "download"

                    print(
                        f"\n➡️ {tr['type']} | FILE={tr['file']} | "
                        f"IP={tr['client_ip']} | SIZE={tr['file_size']} | "
                        f"STATUS={status.upper()}\n"
                    )

                    insert_transfer_db(
                        filename=tr["file"],
                        transfer_type=db_type,
                        status=status,
                        client_ip=tr["client_ip"],
                        file_size=tr["file_size"]
                    )

                    envoyer_syslog(
                        f"Transfert {db_type} | fichier={tr['file']} | "
                        f"IP={tr['client_ip']} | taille={tr['file_size']} bytes | "
                        f"statut={status.upper()}",
                        is_error=(status == "failed")
                    )

                    if error:
                        envoyer_syslog(
                            f"ERREUR sur le transfert {db_type} | fichier={tr['file']} | "
                            f"IP={tr['client_ip']} | PID={tr['pid']} | "
                            f"Raison: {error['reason']}",
                            is_error=True
                        )

                    pending_transfers.remove(tr)
                    if error:
                        log_errors.remove(error)

                    req = next((r for r in log_requests if r["pid"] == tr["pid"]), None)
                    if req:
                        log_requests.remove(req)

if __name__ == "__main__":
    threading.Thread(target=watch_inotify, daemon=True).start()
    threading.Thread(target=watch_logs, daemon=True).start()
    threading.Thread(target=correlate, daemon=True).start()

    while True:
        time.sleep(1)