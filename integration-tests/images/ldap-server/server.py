"""
Minimal in-memory LDAP server using ldaptor.

Serves posixGroup entries under ou=groups,dc=example,dc=com with
anonymous-read access so that CTS's query_ldap_groups() can
retrieve group membership without a bind DN.
"""
import io
from twisted.internet import reactor
from twisted.internet.protocol import ServerFactory
from twisted.python.components import registerAdapter
from ldaptor.inmemory import fromLDIFFile
from ldaptor.interfaces import IConnectedLDAPEntry
from ldaptor.protocols.ldap.ldapserver import LDAPServer

LDIF = b"""\
dn: dc=example,dc=com
dc: example
objectClass: top
objectClass: domain

dn: ou=groups,dc=example,dc=com
ou: groups
objectClass: top
objectClass: organizationalUnit

dn: cn=cts-builders,ou=groups,dc=example,dc=com
cn: cts-builders
objectClass: top
objectClass: posixGroup
gidNumber: 5501
memberUid: builder@example.com

dn: cn=readonly-users,ou=groups,dc=example,dc=com
cn: readonly-users
objectClass: top
objectClass: posixGroup
gidNumber: 5502
memberUid: readonly@example.com

"""


class LDAPServerFactory(ServerFactory):
    protocol = LDAPServer

    def __init__(self, root):
        self.root = root

    def buildProtocol(self, addr):
        proto = self.protocol()
        proto.factory = self
        return proto


registerAdapter(
    lambda f: f.root, LDAPServerFactory, IConnectedLDAPEntry
)


def start(root):
    factory = LDAPServerFactory(root)
    reactor.listenTCP(1389, factory, interface="0.0.0.0")
    print("LDAP server listening on port 1389", flush=True)


d = fromLDIFFile(io.BytesIO(LDIF))
d.addCallback(start)
reactor.run()
