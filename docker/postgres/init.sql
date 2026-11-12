\getenv app_password CRM_APP_PASSWORD
CREATE ROLE crm_app LOGIN PASSWORD :'app_password' NOBYPASSRLS;
CREATE DATABASE crm_test OWNER crm_owner;
GRANT CONNECT ON DATABASE crm TO crm_app;
GRANT CONNECT ON DATABASE crm_test TO crm_app;
