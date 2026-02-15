CREATE DATABASE tftp_logs;

USE tftp_logs;
CREATE TABLE file_transfers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    client_ip VARCHAR(45) NOT NULL,
    file_size BIGINT,
    transfer_type ENUM('upload', 'download') NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) ENUM('success', 'failed') NOT NULL,
    
    INDEX idx_timestamp (timestamp),
    INDEX idx_client (client_ip)
);
