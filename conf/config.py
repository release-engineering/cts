from os import path


# FIXME: workaround for this moment till confdir, dbdir (installdir etc.) are
# declared properly somewhere/somehow
confdir = path.abspath(path.dirname(__file__))
# use parent dir as dbdir else fallback to current dir
dbdir = path.abspath(path.join(confdir, "..")) if confdir.endswith("conf") else confdir


class BaseConfiguration(object):
    # Make this random (used to generate session keys)
    SECRET_KEY = "74d9e9f9cd40e66fc6c4c2e9987dce48df3ce98542529fd0"
    SQLALCHEMY_DATABASE_URI = "sqlite:///{0}".format(path.join(dbdir, "cts.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    HOST = "127.0.0.1"
    PORT = 5005
    SSL_ENABLED = False
    DEBUG = False

    # Select which authentication backend to work with. There are 3 choices
    # noauth: no authentication is enabled. Useful for development particularly.
    # kerberos: Kerberos authentication is enabled.
    # openidc: OpenIDC authentication is enabled.
    AUTH_BACKEND = ""

    # Used for Kerberos authentication and to query user's groups.
    # Format: ldap://hostname[:port]
    # For example: ldap://ldap.example.com/
    AUTH_LDAP_SERVER = ""

    # List of (base, filter) pairs to query groups from LDAP server.
    # CTS can query groups from multi base with different filter, for example:
    # AUTH_LDAP_GROUPS = [
    #     ("ou=groups,dc=example,dc=com", "memberUid={}"),
    #     ("ou=adhoc,ou=managedGroups,dc=example,dc=com", "uniqueMember=uid={},ou=users,dc=example,dc=com")
    # ]
    AUTH_LDAP_GROUPS = []

    AUTH_OPENIDC_USERINFO_URI = "https://id.fedoraproject.org/openidc/UserInfo"

    # Scope requested from Fedora Infra for permission of submitting request to
    # run a new compose.
    # See also: https://fedoraproject.org/wiki/Infrastructure/Authentication
    # Add additional required scope in following list
    #
    # CTS has additional scopes, which will be checked later when specific
    # API is called.
    AUTH_OPENIDC_REQUIRED_SCOPES = [
        "openid",
        "https://id.fedoraproject.org/scope/groups",
    ]

    # Select backend where message will be sent to. Currently, umb is supported
    # which means the Unified Message Bus.
    MESSAGING_BACKEND = ""  # fedora-messaging or umb

    # List of broker URLs. Each of them is a string consisting of domain and
    # optiona port.
    MESSAGING_BROKER_URLS = []

    # Path to certificate file used to authenticate CTS by messaging broker.
    MESSAGING_CERT_FILE = ""

    # Path to private key file used to authenticate CTS by messaging broker.
    MESSAGING_KEY_FILE = ""

    MESSAGING_CA_CERT = ""

    # The MESSAGING_TOPIC is used as topic for messages sent when compose
    # state is change.
    # The INTERNAL_MESSAGING_TOPIC is used for CTS internal messages sent
    # from frontends to backends. It for example triggers removal of expired
    # composes.
    # For umb, it is the ActiveMQ virtual topic e.g.
    # VirtualTopic.eng.cts.state.changed.
    MESSAGING_TOPIC = ""


class DevConfiguration(BaseConfiguration):
    DEBUG = True
    LOG_BACKEND = "console"
    LOG_LEVEL = "debug"
    AUTH_BACKEND = "noauth"
    AUTH_OPENIDC_USERINFO_URI = "https://iddev.fedorainfracloud.org/openidc/UserInfo"


class TestConfiguration(BaseConfiguration):
    LOG_BACKEND = "console"
    LOG_LEVEL = "debug"
    DEBUG = True

    # Use in-memory sqlite db to make tests fast.
    SQLALCHEMY_DATABASE_URI = "sqlite://"

    AUTH_BACKEND = "noauth"
    AUTH_LDAP_SERVER = "ldap://ldap.example.com"
    AUTH_LDAP_GROUP_BASE = "ou=groups,dc=example,dc=com"
    MESSAGING_BACKEND = "rhmsg"


class ProdConfiguration(BaseConfiguration):
    pass
