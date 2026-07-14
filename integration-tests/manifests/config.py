from conf.config import BaseConfiguration

class ProdConfiguration(BaseConfiguration):
    AUTH_BACKEND = "oidc_or_kerberos"
    SQLALCHEMY_DATABASE_URI = "postgresql://cts:cts-test@cts-db:5432/cts"
    AUTH_OPENIDC_USERINFO_URI = "https://dex:5556/userinfo"
    AUTH_OPENIDC_REQUIRED_SCOPES = ["openid"]
    AUTH_LDAP_SERVER = "ldap://openldap:1389"
    AUTH_LDAP_GROUPS = [
        ("ou=groups,dc=example,dc=com", "(&(objectClass=posixGroup)(memberUid={0}))"),
    ]
    ADMINS = {"groups": [], "users": ["builder@example.com"]}
    ALLOWED_BUILDERS = {"groups": [], "users": ["builder@example.com"]}
    MESSAGING_BACKEND = "kafka"
    MESSAGING_BROKER_URLS = ["kafka:9092"]
    MESSAGING_KAFKA_SECURITY_PROTOCOL = "PLAINTEXT"
    MESSAGING_KAFKA_SASL_MECHANISM = ""
    MESSAGING_KAFKA_USERNAME = ""
    MESSAGING_KAFKA_PASSWORD = ""
    MESSAGING_KAFKA_COMPRESSION_TYPE = "none"
    MESSAGING_TOPIC_PREFIX = "cts."
