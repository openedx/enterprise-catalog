CREATE DATABASE IF NOT EXISTS edxapp;
CREATE DATABASE IF NOT EXISTS edxapp_csmh;
GRANT ALL ON edxapp.* TO 'edxapp001'@'%' IDENTIFIED BY 'password';
GRANT ALL ON edxapp_csmh.* TO 'edxapp001'@'%';

FLUSH PRIVILEGES;
