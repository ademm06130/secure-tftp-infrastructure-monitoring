#!/usr/bin/env python3

"""
Configuration example file.
Rename this file to config.py and update values before deployment.
Never commit real credentials to version control.
"""

DB_CONFIG = {
    "host": "localhost",
    "user": "your_database_user",
    "password": "your_database_password",
    "database": "tftp_logs",
    "ssl_disabled": True
}

SYSLOG_CONFIG = {
    "host": "your_server_rsyslog_ip",
    "port": 514
}

TFTP_CONFIG = {
    "root_directory": "/srv/tftp",
    "wait_after_close": 1
}

EMAIL_CONFIG = {
    "smtp_server": "smtp.example.com",
    "smtp_port": 587,
    "sender_email": "your_email@example.com",
    "sender_password": "your_email_password",
    "recipient_email": "admin@example.com"
}

ALERT_CONFIG = {
    "critical_files": [
        "router-prod.cfg",
        "firewall-main.conf",
        "switch-core.cfg",
    ],

    "authorized_ips": [
        "192.168.1.X",
        "192.168.1.Y",
    ],

    "max_requests_per_minute": 15,
    "time_window_seconds": 60,

    "check_interval_seconds": 10
}
