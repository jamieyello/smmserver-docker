from nintendo.nex import backend, service, kerberos, \
    authentication, secure, friends, common
from nintendo.games import Friends
import collections
import itertools
import secrets
import time
import argparse
import logging
import configparser
import os
import sys

# https://stackoverflow.com/a/44175370/1806760
logging.basicConfig(
    format="[%(asctime)s] %(levelname)s: %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# Config setup to match SMM server logic
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(CURRENT_DIR))

CONFIGS_DIR = os.path.join(ROOT_DIR, 'Configs')
INI_PATH = os.path.join(CONFIGS_DIR, 'Pretendo++.ini')

def get_bind_ip():
    """Address the friends servers listen on. SMM_BIND_IP overrides it (a container uses 0.0.0.0)."""
    if os.environ.get('SMM_BIND_IP'):
        return os.environ['SMM_BIND_IP']
    config = configparser.ConfigParser()
    try:
        if os.path.exists(INI_PATH):
            config.read(INI_PATH)
            if config.has_section('00003200'):
                return config.get('00003200', 'host', fallback='127.0.5.1')
    except:
        pass
    return '127.0.5.1'

BIND_IP = get_bind_ip()
# Address the game is told to connect to (SMM_PUBLIC_IP; a container must set it to its host's address)
PUBLIC_IP = os.environ.get('SMM_PUBLIC_IP') or BIND_IP

User = collections.namedtuple("User", "pid name password")

users = [
    User(2, "Quazal Rendez-Vous", "password"),
    User(100, "guest", "MMQea3n!fsik"),
    User(1337, "1337", "password"),
    # More accounts here
]


def get_user_by_name(name):
    for user in users:
        if user.name == name:
            return user


def get_or_add_player(name):
    """The game logs in with the player ID of the console's account as the username (for example 1712680340), which is
    different on every console, so a fixed list of users cannot cover it. A numeric username becomes a player on the
    fly. The password is the one account_server.py puts in the NEX token ("password"), so both sides derive the same key."""
    user = get_user_by_name(name)
    if user is None and name.isdigit() and 1000 <= int(name) < 2**32:
        user = User(int(name), name, "password")
        users.append(user)
        logger.info("new player {}".format(name))
    return user
def get_user_by_pid(pid):
    for user in users:
        if user.pid == pid:
            return user


def derive_key(user):
    deriv = kerberos.KeyDerivationOld(65000, 1024)
    return deriv.derive_key(user.password.encode("ascii"), user.pid)


SECURE_SERVER = "Quazal Rendez-Vous"


class AuthenticationServer(authentication.AuthenticationServer):
    def __init__(self, settings, secure_host, secure_port):
        super().__init__()
        self.settings = settings
        self.secure_host = secure_host
        self.secure_port = secure_port

    def login(self, context, username):
        logger.info("User trying to log in: {}".format(username))

        user = get_or_add_player(username)
        if not user:
            raise common.RMCError("RendezVous::InvalidUsername")

        server = get_user_by_name(SECURE_SERVER)

        url = common.StationURL(
            scheme="prudps", address=self.secure_host, port=self.secure_port,
            PID=server.pid, CID=1, type=2,
            sid=1, stream=10
        )

        conn_data = authentication.RVConnectionData()
        conn_data.main_station = url
        conn_data.special_protocols = []
        conn_data.special_station = common.StationURL()

        response = common.RMCResponse()
        response.result = common.Result(0x10001)  # Success
        response.pid = user.pid
        response.ticket = self.generate_ticket(user, server)
        response.connection_data = conn_data
        response.server_name = "branch:origin/project/nfs build:3_10_18_2006_0"
        return response

    def request_ticket(self, context, source, target):
        source = get_user_by_pid(source)
        target = get_user_by_pid(target)

        response = common.RMCResponse()
        response.result = common.Result(0x10001)  # Success
        response.ticket = self.generate_ticket(source, target)
        return response

    def generate_ticket(self, source, target):
        settings = self.settings

        user_key = derive_key(source)
        server_key = derive_key(target)
        session_key = secrets.token_bytes(settings.get("kerberos.key_size"))

        internal = kerberos.ServerTicket()
        internal.expiration = common.DateTime.fromtimestamp(time.time() + 120)
        internal.source_pid = source.pid
        internal.session_key = session_key

        ticket = kerberos.ClientTicket()
        ticket.session_key = session_key
        ticket.target_pid = 1
        ticket.internal = internal.encrypt(server_key, settings)

        return ticket.encrypt(user_key, settings)


class SecureConnectionServer(secure.SecureConnectionServer):
    def __init__(self):
        super().__init__()
        self.connection_id = itertools.count(10)

    def register(self, context, urls):
        addr = context.client.remote_address()
        station = urls[0].copy()
        station["address"] = addr[0]
        station["port"] = addr[1]
        station["type"] = 3

        response = common.RMCResponse()
        response.result = common.Result(0x10001)  # Success
        response.connection_id = next(self.connection_id)
        response.public_station = station
        return response

    def register_ex(self, context, urls, login_data):
        return self.register(context, urls)


class FriendsServer(friends.FriendsServer):
    def __init__(self):
        super(FriendsServer, self).__init__()

    def get_all_information(self, context, nna_info, presence, birthday):
        logger.info("FriendsServer.get_all_information(pid: %d, call_id: %d, nna_info: %s, presence: %s, birthday: %s" % (context.pid, context.client.call_id, nna_info, presence, birthday))
        principal_preference = friends.PrincipalPreference()
        principal_preference.unk1 = True
        principal_preference.unk2 = True
        principal_preference.unk3 = False

        comment = friends.Comment()
        comment.unk = 0
        comment.text = ""
        comment.changed = common.DateTime(0)

        response = common.RMCResponse()
        response.principal_preference = principal_preference
        response.comment = comment
        response.friends = []
        response.sent_requests = []
        response.received_requests = []
        response.blacklist = []
        response.unk1 = False
        response.notifications = []
        response.unk2 = False
        return response

    def update_presence(self, context, presence):
        logger.info("FriendsServer.update_presence (noop ack)")

    def update_mii(self, context, mii):
        logger.info("FriendsServer.update_mii (noop ack)")

    def update_comment(self, context, comment):
        logger.info("FriendsServer.update_comment (noop ack)")

    def update_preference(self, context, preference):
        logger.info("FriendsServer.update_preference (noop ack)")

    def handle_update_mii(self, context, input, output):
        logger.info("FriendsServer.handle_update_mii (noop ack)")

    def handle_update_comment(self, context, input, output):
        logger.info("FriendsServer.handle_update_comment (noop ack)")

    def handle_update_preference(self, context, input, output):
        logger.info("FriendsServer.handle_update_preference (noop ack)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-host", default=BIND_IP, help="hostname/ip to host the server on")
    parser.add_argument("-pid", type=int, help="additional user pid")
    parser.add_argument("-username", help="additional user username")
    parser.add_argument("-password", help="additional user password")
    args = parser.parse_args()
    host = args.host
    if args.pid and args.username and args.password:
        users.append(User(args.pid, args.username, args.password))

    settings = backend.Settings("friends.cfg")
    settings.set("nex.access_key", Friends.ACCESS_KEY)
    settings.set("prudp.ping_timeout", 30.0)

    server_key = derive_key(get_user_by_name(SECURE_SERVER))
    secure_server = service.RMCServer(settings)
    secure_server.register_protocol(SecureConnectionServer())
    secure_server.register_protocol(FriendsServer())
    secure_server.start(host, 60021, key=server_key)
    logger.info("friends secure server {}:60021".format(host))

    auth_server = service.RMCServer(settings)
    auth_server.register_protocol(AuthenticationServer(settings, PUBLIC_IP if host == BIND_IP else host, 60021))
    auth_server.start(host, 60000)
    logger.info("friends auth server {}:60000".format(host))

    logger.info("Press Ctrl+C to exit...")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
