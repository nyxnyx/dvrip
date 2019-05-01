#!/usr/bin/env python3

from getopt import GetoptError, getopt
from getpass import getpass
from os import environ
from os.path import basename
from socket import AF_INET, SOCK_STREAM, socket as Socket, gethostbyname, \
                   getservbyname
from sys import argv, executable, exit, stderr, stdout  # pylint: disable=redefined-builtin
from typing import List, NoReturn, TextIO
from .errors import DVRIPDecodeError, DVRIPRequestError
from .io import DVRIPClient

try:
	# pylint: disable=ungrouped-imports
	from os import EX_USAGE, EX_NOHOST, EX_IOERR, EX_PROTOCOL
except ImportError:  # BSD value  # pragma: no cover
	EX_USAGE    = 64
	EX_NOHOST   = 68
	EX_IOERR    = 74
	EX_PROTOCOL = 76



def prog():
	name = basename(argv[0])
	return ('{} -m dvrip'.format(executable)
	        if name in {'__main__.py', '-c'}
	        else name)


def ioerr(e, code=EX_IOERR):
	message = ('{}: {}'.format(e.filename, e.strerror) \
	           if e.filename is not None else e.strerror)
	print(message, file=stderr)
	exit(code)


def connect(host: str, port: str, user: str, password: str) -> DVRIPClient:
	try:
		serv = int(port, base=0)
	except ValueError:
		try:
			serv = getservbyname(port)
		except OSError as e:
			ioerr(e, EX_NOHOST)

	try:
		host = gethostbyname(host)
	except OSError as e:
		ioerr(e, EX_NOHOST)

	conn = DVRIPClient(Socket(AF_INET, SOCK_STREAM))
	try:
		conn.connect((host, serv), user, password)
	except DVRIPDecodeError as e:
		print(e, file=stderr)
		exit(EX_PROTOCOL)
	except DVRIPRequestError as e:
		print(e, file=stderr)
		exit(2)  # FIXME more granular codes
	except OSError as e:
		ioerr(e)

	return conn


def run_info(conn: DVRIPClient, args: List[str]) -> None:  # pylint: disable=too-many-branches,too-many-locals
	if args:
		fail = tuple(args) != ('-h',)
		print('Usage: {} ... info'.format(prog()),
		      file=stderr if fail else stdout)
		exit(EX_USAGE if fail else 0)

	info = conn.systeminfo()
	line = [info.chassis, info.board, info.serial]
	for attr in ('hardware', 'eeprom', 'software', 'build', 'videoin',
	             'videoout', 'commin', 'commout', 'triggerin',
	             'triggerout', 'audioin', 'views'):
		value = getattr(info, attr)
		if value:
			line.append('{} {}'.format(attr, value))
	print(' '.join(line))  # system line

	for disk in conn.storageinfo():
		print('disk {}'.format(disk.number))  # disk group
		for i, part in zip(range(disk.parts), disk.partinfo):
			line = ['  part {}'.format(i)]
			if part.current:
				line.append('current')
			line.append('size {}M free {}M'
			            .format(part.size, part.free))
			for attr in ('viewedstart', 'viewedend',
			             'unviewedstart', 'unviewedend'):
				date = getattr(part, attr)
				line.append('{} {}'
				            .format(attr, date.isoformat()))
			print(' '.join(line))  # partition line

	actv = conn.activityinfo()
	line = []
	for i, chan in zip(range(info.videoin), actv.channels):
		print('channel {} bitrate {}K/s'.format(i, chan.bitrate) +
		      (' recording' if chan.recording else ''))

	line = []
	line.append(conn.time().isoformat())
	minutes = info.uptime
	hours, minutes = divmod(minutes, 60)
	days, hours = divmod(hours, 24)
	if days:
		line.append("up P{}dT{:02}h{:02}m".format(days, hours, minutes))
	else:
		line.append("up PT{}h{:02}m".format(hours, minutes))
	line.append('triggers')
	for attr in ('in_', 'out', 'obscure', 'disconnect', 'motion'):
		value = getattr(actv.triggers, attr)
		if value:
			line.append('{} {}'.format(attr.rstrip('_'), value))
	if len(line) <= 3:
		line.append('none')
	print(' '.join(line))  # status line


def run_time(conn: DVRIPClient, args: List[str]) -> None:
	from dateparser import parse as dateparse  # type: ignore

	time = dateparse(args[0] if args else '1970-01-01')
	if len(args) > 2 or time is None or time.tzinfo is not None:
		print('Usage: {} ... time [TIME]'.format(prog()))
		exit(EX_USAGE)

	print((conn.time(time) if args else conn.time()).isoformat())


def usage(code: int = EX_USAGE, file: TextIO = stderr) -> NoReturn:
	print('Usage: {} [-p PORT] [-u USERNAME] HOST COMMAND ...'
	      .format(prog()),
	      file=file, flush=True)
	exit(code)


def run(args: List[str] = argv[1:]) -> None:  # pylint: disable=dangerous-default-value,too-many-branches
	try:
		opts, args = getopt(args, 'hp:u:')
	except GetoptError:
		usage()
	if len(args) < 2:
		usage()
	host, command, *args = args
	if not all(c.isalnum() or c == '-' for c in command):
		usage()

	port = environ.get('DVR_PORT', '34567')
	username = environ.get('DVR_USERNAME', 'admin')
	for opt, arg in opts:
		if opt == '-p':
			port = arg
		if opt == '-u':
			username = arg
		if opt == '-h':
			if len(opts) != 1:
				usage()
			usage(0, file=stdout)

	password = environ.get('DVR_PASSWORD', None)
	if password is None:
		try:
			password = getpass('Password: ')
		except EOFError:
			exit(EX_IOERR)

	if command == 'reboot':
		conn = connect(host, port, username, password)
		conn.reboot()
	elif command == 'info':
		conn = connect(host, port, username, password)
		try:
			run_info(conn, args)
		finally:
			conn.logout()
	elif command == 'time':
		conn = connect(host, port, username, password)
		try:
			run_time(conn, args)
		finally:
			conn.logout()
	else:
		usage()


if __name__ == '__main__':
	run()
