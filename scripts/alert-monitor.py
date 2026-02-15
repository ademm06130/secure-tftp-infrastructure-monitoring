#!/usr/bin/env python3
import time
import smtplib
import mysql.connector
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from collections import defaultdict

from config import DB_CONFIG, EMAIL_CONFIG, ALERT_CONFIG

last_checked_id = 0
request_tracker = defaultdict(list)

def connecter_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"[DB CONNECTION ERROR] ❌ {e}")
        return None

def envoyer_email(sujet, corps):
    """Envoie une alerte par email"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG["sender_email"]
        msg['To'] = EMAIL_CONFIG["recipient_email"]
        msg['Subject'] = sujet

        msg.attach(MIMEText(corps, 'plain'))

        server = smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"])
        server.starttls()
        server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])

        server.send_message(msg)
        server.quit()

        print(f"[EMAIL] ✅ Alerte envoyée : {sujet}")
    except Exception as e:
        print(f"[EMAIL ERROR] ❌ {e}")

# ==============================
# DÉTECTION D'ANOMALIES
# ==============================
def verifier_ip_non_autorisee(client_ip, filename, transfer_id):
    """Vérifie si l'IP est dans la liste blanche"""
    if client_ip not in ALERT_CONFIG["authorized_ips"]:
        message = (
            f" ALERTE : IP NON AUTORISÉE\n"
            f"IP source : {client_ip}\n"
            f"Fichier : {filename}\n"
            f"ID transfert : {transfer_id}\n"
            f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        print(f"\n[ANOMALIE] ⚠️ IP non autorisée détectée : {client_ip}\n")

        envoyer_email(
            f" ALERTE SÉCURITÉ - IP Non Autorisée : {client_ip}",
            message
        )

        return True
    return False

def verifier_fichier_critique(filename, client_ip, transfer_id):
    """Vérifie si un fichier critique a été accédé"""
    if filename in ALERT_CONFIG["critical_files"]:
        message = (
            f"⚠ ALERTE : ACCÈS À UN FICHIER CRITIQUE\n"
            f"Fichier : {filename}\n"
            f"IP source : {client_ip}\n"
            f"ID transfert : {transfer_id}\n"
            f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        print(f"\n[ANOMALIE]  Fichier critique accédé : {filename} par {client_ip}\n")

        envoyer_email(
            f"⚠️ALERTE - Accès Fichier Critique : {filename}",
            message
        )

        return True
    return False

def verifier_rate_limit(client_ip, filename, transfer_id, timestamp):
    """Vérifie si une IP fait trop de requêtes dans un court laps de temps"""
    global request_tracker

    now = datetime.now()
    time_window = timedelta(seconds=ALERT_CONFIG["time_window_seconds"])

    # Ajouter la requête actuelle
    request_tracker[client_ip].append(timestamp)

    # Nettoyer les anciennes requêtes (hors de la fenêtre de temps)
    request_tracker[client_ip] = [
        ts for ts in request_tracker[client_ip]
        if now - ts < time_window
    ]

    # Compter les requêtes dans la fenêtre
    count = len(request_tracker[client_ip])

    if count > ALERT_CONFIG["max_requests_per_minute"]:
        message = (
            f" ALERTE : TROP DE REQUÊTES\n"
            f"IP source : {client_ip}\n"
            f"Nombre de requêtes : {count} requêtes en {ALERT_CONFIG['time_window_seconds']} secondes\n"
            f"Seuil autorisé : {ALERT_CONFIG['max_requests_per_minute']} requêtes/minute\n"
            f"Dernier fichier accédé : {filename}\n"
            f"ID transfert : {transfer_id}\n"
            f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        print(f"\n[ANOMALIE]  Trop de requêtes détectées depuis {client_ip} : {count} requêtes\n")

        envoyer_email(
            f" ALERTE - Rate Limit Dépassé : {client_ip}",
            message
        )

        # Réinitialiser le compteur pour éviter le spam d'alertes
        request_tracker[client_ip] = []

        return True

    return False

# ==============================
# BOUCLE PRINCIPALE
# ==============================
def surveiller_anomalies():
    """Boucle principale de détection d'anomalies"""
    global last_checked_id

    print(" Démarrage de la surveillance des anomalies...")

    # Initialiser last_checked_id au dernier ID existant pour éviter de traiter l'historique
    try:
        conn = connecter_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(id) as max_id FROM file_transfers")
            result = cursor.fetchone()
            last_checked_id = result[0] if result[0] is not None else 0
            cursor.close()
            conn.close()
            print(f" Démarrage à partir de l'ID : {last_checked_id}")
    except Exception as e:
        print(f"[WARN] ⚠️Impossible de récupérer le dernier ID : {e}")
        last_checked_id = 0

    print(f" IPs autorisées : {', '.join(ALERT_CONFIG['authorized_ips'])}")
    print(f" Fichiers critiques : {', '.join(ALERT_CONFIG['critical_files'])}")
    print(f" Rate limit : {ALERT_CONFIG['max_requests_per_minute']} requêtes par minute\n")

    while True:
        try:
            conn = connecter_db()
            if not conn:
                print("[ERROR]  Impossible de se connecter à la base de données")
                time.sleep(ALERT_CONFIG["check_interval_seconds"])
                continue

            cursor = conn.cursor(dictionary=True)

            # Récupérer les nouveaux transferts depuis le dernier ID vérifié
            query = """
                SELECT id, filename, client_ip, timestamp
                FROM file_transfers
                WHERE id > %s
                ORDER BY id ASC
            """
            cursor.execute(query, (last_checked_id,))
            transfers = cursor.fetchall()

            for transfer in transfers:
                transfer_id = transfer['id']
                filename = transfer['filename']
                client_ip = transfer['client_ip']
                transfer_time = transfer['timestamp']

                print(f"[CHECK]  Analyse transfert #{transfer_id} : {filename} depuis {client_ip}")

                # Vérifier les 3 types d'anomalies
                verifier_ip_non_autorisee(client_ip, filename, transfer_id)
                verifier_fichier_critique(filename, client_ip, transfer_id)
                verifier_rate_limit(client_ip, filename, transfer_id, transfer_time)

                # Mettre à jour le dernier ID vérifié
                last_checked_id = transfer_id

            cursor.close()
            conn.close()

            if transfers:
                print(f"✅ {len(transfers)} transfert(s) analysé(s)\n")

        except Exception as e:
            print(f"[ERROR] ❌ Erreur lors de la surveillance : {e}")

        # Attendre avant la prochaine vérification
        time.sleep(ALERT_CONFIG["check_interval_seconds"])

# ==============================
# POINT D'ENTRÉE
# ==============================
if __name__ == "__main__":
    surveiller_anomalies()