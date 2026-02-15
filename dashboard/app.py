#!/usr/bin/env python3
"""
Dashboard Web Flask pour la supervision du serveur TFTP
Version CORRIGÉE avec bug fix
"""

from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
import mysql.connector
import subprocess
import psutil
from config import DB_CONFIG

app = Flask(__name__)


def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"[DB ERROR] ❌ {e}")
        return None


def get_server_status():
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)

        # RAM
        memory = psutil.virtual_memory()
        ram_percent = memory.percent
        ram_used = round(memory.used / (1024**3), 2)  # GB
        ram_total = round(memory.total / (1024**3), 2)  # GB

        # Disque
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used = round(disk.used / (1024**3), 2)  # GB
        disk_total = round(disk.total / (1024**3), 2)  # GB

        # Uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        uptime_str = f"{uptime.days}j {uptime.seconds//3600}h {(uptime.seconds//60)%60}m"

        return {
            'cpu_percent': cpu_percent,
            'ram_percent': ram_percent,
            'ram_used': ram_used,
            'ram_total': ram_total,
            'disk_percent': disk_percent,
            'disk_used': disk_used,
            'disk_total': disk_total,
            'uptime': uptime_str
        }
    except Exception as e:
        print(f"[SERVER STATUS ERROR] ❌ {e}")
        return None


def get_service_status(service_name):
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True,
            text=True
        )
        status = result.stdout.strip()

        status_result = subprocess.run(
            ['systemctl', 'status', service_name],
            capture_output=True,
            text=True
        )

        pid = None
        for line in status_result.stdout.split('\n'):
            if 'Main PID:' in line:
                pid = line.split('Main PID:')[1].split()[0]
                break

        return {
            'name': service_name,
            'status': status,
            'active': status == 'active',
            'pid': pid
        }
    except Exception as e:
        print(f"[SERVICE STATUS ERROR] ❌ {e}")
        return {
            'name': service_name,
            'status': 'unknown',
            'active': False,
            'pid': None
        }

def get_all_services_status():
    services = [
        'tftpd-hpa',
        'tftp-monitor',
        'tftp-alert',
        'tftp-dashboard',
        'mysql',
        'rsyslog'
    ]

    return [get_service_status(service) for service in services]


def get_statistics():
    """Récupère les statistiques générales"""
    conn = get_db_connection()
    if not conn:
        return None

    cursor = conn.cursor(dictionary=True)
    stats = {}

    # ✅ FIX: Récupération correcte du total aujourd'hui
    cursor.execute("""
        SELECT COUNT(*) as total
        FROM file_transfers
        WHERE DATE(timestamp) = CURDATE()
    """)
    stats['today_total'] = cursor.fetchone()['total']  # ✅ LIGNE AJOUTÉE

    cursor.execute("""
        SELECT COUNT(*) as success
        FROM file_transfers
        WHERE DATE(timestamp) = CURDATE() AND status = 'success'
    """)
    stats['today_success'] = cursor.fetchone()['success']

    cursor.execute("""
        SELECT COUNT(*) as failed
        FROM file_transfers
        WHERE DATE(timestamp) = CURDATE() AND status = 'failed'
    """)
    stats['today_failed'] = cursor.fetchone()['failed']

    if stats['today_total'] > 0:
        stats['success_rate'] = round((stats['today_success'] / stats['today_total']) * 100, 1)
    else:
        stats['success_rate'] = 0

    cursor.execute("""
        SELECT COUNT(DISTINCT client_ip) as active_ips
        FROM file_transfers
        WHERE DATE(timestamp) = CURDATE()
    """)
    stats['active_ips'] = cursor.fetchone()['active_ips']

    cursor.execute("SELECT COUNT(*) as total FROM file_transfers")
    stats['total_all_time'] = cursor.fetchone()['total']

    cursor.close()
    conn.close()

    return stats


def get_recent_transfers(limit=20):
    conn = get_db_connection()
    if not conn:
        return []

    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, filename, client_ip, file_size, transfer_type, status, timestamp
        FROM file_transfers
        ORDER BY id DESC
        LIMIT %s
    """, (limit,))

    transfers = cursor.fetchall()

    for transfer in transfers:
        transfer['timestamp'] = transfer['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        transfer['file_size'] = f"{transfer['file_size']:,}" if transfer['file_size'] else "N/A"

    cursor.close()
    conn.close()

    return transfers


def get_hourly_stats():
    """Récupère les stats par heure pour les dernières 24h"""
    conn = get_db_connection()
    if not conn:
        return []

    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            HOUR(timestamp) as hour,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM file_transfers
        WHERE timestamp >= NOW() - INTERVAL 24 HOUR
        GROUP BY HOUR(timestamp)
        ORDER BY hour
    """)

    stats = cursor.fetchall()

    cursor.close()
    conn.close()

    return stats


def get_top_files(limit=5):
    """Récupère les fichiers les plus transférés"""
    conn = get_db_connection()
    if not conn:
        return []

    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT filename, COUNT(*) as count
        FROM file_transfers
        GROUP BY filename
        ORDER BY count DESC
        LIMIT %s
    """, (limit,))

    files = cursor.fetchall()

    cursor.close()
    conn.close()

    return files



@app.route('/')
def index():
    """Page principale du dashboard"""
    stats = get_statistics()
    transfers = get_recent_transfers(20)
    server_status = get_server_status()
    services_status = get_all_services_status()

    return render_template('dashboard.html',
                         stats=stats,
                         transfers=transfers,
                         server=server_status,
                         services=services_status)

@app.route('/api/stats')
def api_stats():
    """API JSON pour les statistiques"""
    return jsonify(get_statistics())

@app.route('/api/server')
def api_server():
    """API JSON pour le statut du serveur"""
    return jsonify(get_server_status())

@app.route('/api/services')
def api_services():
    """API JSON pour le statut des services"""
    return jsonify(get_all_services_status())

@app.route('/api/transfers')
def api_transfers():
    """API JSON pour les derniers transferts"""
    return jsonify(get_recent_transfers(50))

@app.route('/api/hourly')
def api_hourly():
    """API JSON pour les stats horaires"""
    return jsonify(get_hourly_stats())

@app.route('/api/top-files')
def api_top_files():
    """API JSON pour les fichiers les plus transférés"""
    return jsonify(get_top_files())


if __name__ == '__main__':
    print("🌐 Démarrage du dashboard web...")
    app.run(host='0.0.0.0', port=5000, debug=False)