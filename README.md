#  Secure TFTP Infrastructure with Multi-Threaded Monitoring & Centralized Logging

##  Project Context

This project was developed during my internship within a Cybersecurity & Infrastructure department.

The objective was to design a secure and fully monitored TFTP infrastructure capable of:

- Real-time transfer tracking
- Compensating for TFTP protocol limitations
- Detecting failed transfers
- Centralizing logs on a remote server
- Triggering automated alerts
- Providing operational visibility via a web dashboard

---

##  Technical Challenge

The TFTP protocol is extremely lightweight and does not provide explicit transfer states.

Standard logs only contain:

- `RRQ` (Read Request)
- `WRQ` (Write Request)

There are no explicit messages indicating:

- Transfer success
- Transfer completion
- Transfer failure confirmation
- Pending status

Therefore, a custom monitoring and correlation engine was implemented.

---

##  Monitoring Engine Design

The monitoring system is built using a **multi-threaded architecture** combining log analysis and filesystem event detection.

###  Thread 1 — Log Monitoring (journalctl)

Continuously reads:

```
journalctl -u tftpd-hpa -f
```

Extracts:

- Process ID (PID)
- Transfer type (RRQ / WRQ)
- Client IP
- Requested filename

Also detects error patterns:

- `Connection refused`
- `NAK` responses

All detected requests are stored temporarily in memory.

---

###  Thread 2 — Filesystem Monitoring (inotify)

Uses `inotifywait` to monitor:

- `CLOSE_WRITE`
- `CLOSE_NOWRITE`

inside the TFTP root directory.

Detects:

- File creation
- File close events
- File modification completion

This provides real filesystem confirmation of transfer activity.

---

###  Thread 3 — Correlation Engine

A dedicated correlation loop:

1. Matches log requests with inotify events
2. Verifies correct event type:
   - WRQ → CLOSE_WRITE
   - RRQ → CLOSE_NOWRITE
3. Retrieves file size
4. Applies a stabilization delay (`WAIT_AFTER_CLOSE`)
5. Checks if related errors were logged (NAK / refused)
6. Determines final status:
   - `success`
   - `failed`

This dual-source validation ensures accurate transfer state determination.

---

##  Database Logging

Once validated, transfer metadata is inserted into MySQL:

- Filename
- Client IP
- File size
- Transfer type (upload / download)
- Status (success / failed)

This provides structured historical tracking.

---

##  Remote Syslog Forwarding

After validation, the script sends structured logs to a **remote rsyslog server** (separate machine).

Communication:

- UDP socket
- Custom syslog priority:
  - Normal transfers
  - Error transfers (higher severity)

The remote server:

- Receives transfer status logs
- Stores them dynamically by:
  - Source IP
  - Date

This ensures:

- Centralized log retention
- Improved forensic capabilities
- Infrastructure resilience

---

##  Error Handling

The script detects and classifies:

- Connection refused
- NAK responses

If an error is detected:

- Transfer marked as failed
- Error logged in database
- High-priority syslog message sent
- Detailed error message forwarded

---

##  Operational Flow

1. Device sends RRQ / WRQ request.
2. journalctl thread captures request.
3. inotify thread detects file close event.
4. Correlation engine validates event.
5. File size retrieved.
6. Status determined.
7. Metadata inserted into MySQL.
8. Structured syslog message sent to remote server.
9. Dashboard updates in real time.

---

##  Web Dashboard

Developed using Flask.

Provides:

- Real-time transfer monitoring
- Transfers per hour statistics
- Historical logs
- Most requested files
- Server uptime
- CPU / RAM / Disk usage
- systemd service status

Auto-refresh mechanism included.

---

##  Security Enhancements

Although TFTP lacks authentication and encryption, the infrastructure is reinforced by:

- UFW IP filtering
- Remote log centralization
- Multi-source event correlation
- Error detection engine
- Automated email alerts (separate alert script)
- Restricted database privileges
- systemd service isolation

---

##  Alert System

A separate alert script analyzes database patterns and detects:

- Unauthorized IP addresses
- Access to critical configuration files
- Excessive request frequency

When triggered:

- Email alert sent via SMTP
- Event logged and forwarded to remote syslog server

---

##  Testing Environment

Validated using Cisco devices in GNS3.

Confirmed:

- RRQ / WRQ detection accuracy
- inotify correlation reliability
- File size stabilization
- Error detection logic
- Database integrity
- Remote syslog forwarding
- Email alert triggering

---

##  Technical Skills Demonstrated

- Linux system administration
- TFTP protocol analysis
- Multi-threaded Python programming
- Real-time log parsing
- Filesystem event monitoring (inotify)
- Event correlation architecture
- MySQL integration
- Remote syslog communication (UDP sockets)
- Error classification logic
- Infrastructure monitoring design
- Security-focused system architecture

---

##  Security Notice

Sensitive credentials and production configuration files are excluded.

`config_example.py` is provided for demonstration.

---

##  Author

Adem Mathlouthi  
Network & Cybersecurity Student
