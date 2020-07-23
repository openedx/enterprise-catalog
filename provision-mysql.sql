CREATE DATABASE IF NOT EXISTS enterprise_catalog;
GRANT ALL ON enterprise_catalog.* TO 'entcatalog001'@'%' IDENTIFIED BY 'password';

CREATE DATABASE IF NOT EXISTS discovery;
GRANT ALL ON discovery.* TO 'discov001'@'%' IDENTIFIED BY 'password';

CREATE DATABASE IF NOT EXISTS edxapp;
CREATE DATABASE IF NOT EXISTS edxapp_csmh;
GRANT ALL ON edxapp.* TO 'edxapp001'@'%' IDENTIFIED BY 'password';
GRANT ALL ON edxapp_csmh.* TO 'edxapp001'@'%';

# TODO: Remove this and find a better home.
--
-- Dumping data for table `django_site`
--

LOCK TABLES `django_site` WRITE;
/*!40000 ALTER TABLE `django_site` DISABLE KEYS */;
INSERT INTO `django_site` VALUES (1,'example.com','example.com');
/*!40000 ALTER TABLE `django_site` ENABLE KEYS */;
UNLOCK TABLES;

FLUSH PRIVILEGES;