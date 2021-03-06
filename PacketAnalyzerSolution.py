import socket,os,struct,binascii,sys,string,base64,pygeoip,threading,time

class bcolors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

gi = pygeoip.GeoIP('/opt/GeoIP/GeoLiteCity.dat')
sock_created = False
sniffer_socket = 0
src_ip = ""
dst_ip = ""
dos = {}

def analyze_udp_header(recv_data):
	udp_hdr  = struct.unpack("!4H",recv_data[:8])
	src_port = udp_hdr[0]
	dst_port = udp_hdr[1]
	length   = udp_hdr[2]
	chk_sum  = udp_hdr[3]
	data     = recv_data[8:]

	#print ("|=============================UDP HEADER==================================|")
	#print ("|\tSource:\t\t%u" % src_port)
	#print ("|\tDest:\t\t%u" % dst_port)
	#print ("|\tLength:\t\t%u" % length)
	#print ("|\tChecksum:\t\t%u" % chk_sum)

	return data

def analyze_tcp_header(recv_data):
	tcp_hdr  = struct.unpack("!2H2I4H",recv_data[:20])
	src_port = tcp_hdr[0]
	dst_port = tcp_hdr[1]
	seq_num  = tcp_hdr[2]
	ack_num  = tcp_hdr[3]
	data_off = tcp_hdr[4] & 0xf000
	reserved = tcp_hdr[4] & 0xF00
	flags    = tcp_hdr[4] & 0xFF
	win_size = tcp_hdr[5]
	chk_sum  = tcp_hdr[6]
	urg_ptr  = tcp_hdr[7]
	data     = recv_data[20:]

	urg = bool(flags & 0x20)
	ack = bool(flags & 0x10)
	psh = bool(flags & 0x8)
	rst = bool(flags & 0x4)
	syn = bool(flags & 0x2)
	fin = bool(flags & 0x1)

	#print ("|=============================TCP HEADER==================================|")
	#print ("|\tSource:\t\t%u" % src_port)
	#print ("|\tDest:\t\t%u" % dst_port)
	#print ("|\tSeq:\t\t%u" % seq_num)
	#print ("|\tAck:\t\t%u" % ack_num)
	#print ("|\tFlags-->")
	#print ("|\tURG:\t\t%u" % urg)
	#print ("|\tACK:\t\t%u" % ack)
	#print ("|\tPSH:\t\t%u" % psh)
	#print ("|\tRST:\t\t%u" % rst)
	#print ("|\tSYN:\t\t%u" % syn)
	#print ("|\tFIN:\t\t%u" % fin)
	#print ("|\tWindow:\t\t%u" % win_size)
	#print ("|\tChecksum:\t%u" % chk_sum)

	return data

def analyze_ip_header(recv_data):
	global src_ip
	global dst_ip
	ip_hdr      = struct.unpack("!6H4s4s",recv_data[:20])
	ver         = ip_hdr[0] >> 12
	hdr_len     = ip_hdr[0] & 0x0f00
	ip_tos      = ip_hdr[0] & 0xff
	tot_len     = ip_hdr[1]
	ip_id       = ip_hdr[2]
	flag        = ip_hdr[3] & 0xe000
	offset      = ip_hdr[3] & 0x1fff
	ttl         = ip_hdr[4] >> 8
	ip_proto    = ip_hdr[4] & 0x00ff
	ip_cksum    = ip_hdr[5]
	src_ip      = socket.inet_ntoa(ip_hdr[6])
	dst_ip      = socket.inet_ntoa(ip_hdr[7])
	data        = recv_data[20:]

	#print ("|=============================IP HEADER===================================|")
	#print ("|\tVersion:\t%u" % ver)
	#print ("|\tIHL:\t\t%u" % hdr_len)
	#print ("|\tTOS:\t\t%u" % ip_tos)
	#print ("|\tLength:\t\t%u" % tot_len)
	#print ("|\tID:\t\t%u" % ip_id)
	#print ("|\tflag:\t\t%u" % flag)
	#print ("|\toffset:\t\t%u" % offset)
	#print ("|\tTTL:\t\t%u" % ttl)
	#print ("|\tNext protocol:\t%u" % ip_proto)
	#print ("|\tChecksum:\t%u" % ip_cksum)
	#print ("|\tsource ip:\t%s |\tdest ip:\t%s" % (src_ip ,dst_ip))
	rec_src = gi.record_by_name(src_ip)
	rec_dst = gi.record_by_name(dst_ip)
	if rec_src:
		s = rec_src['country_name']
	else:
		s = ""
	if rec_dst:
		d = rec_dst['country_name']
	else:
		d = ""
	#print ("\t %s (%s)  ->>>  %s (%s)" % (src_ip ,s ,dst_ip ,d))
	if ip_proto == 6:
		tcp_udp = "tcp"
	elif ip_proto == 17:
		tcp_udp = "udp"
	else:
		tcp_udp = "other"

	return data,tcp_udp

def analyze_ether_header(recv_data):
	eth_hdr  = struct.unpack("!6s6sH",recv_data[:14])
	dst_mac  = binascii.hexlify(eth_hdr[0])
	src_mac  = binascii.hexlify(eth_hdr[1])
	proto    = eth_hdr[2]
	data     = recv_data[14:]

	#print ("|=============================ETHERNET HEADER=============================|")
	#print ("|\tDest:\t\t%s:%s:%s:%s:%s:%s" % (dst_mac[:2],dst_mac[2:4],dst_mac[4:6],dst_mac[6:8],dst_mac[8:10],dst_mac[10:12]))
	#print ("|\tSource:\t\t%s:%s:%s:%s:%s:%s" % (src_mac[:2],src_mac[2:4],src_mac[4:6],src_mac[6:8],src_mac[8:10],src_mac[10:12]))

	if proto == 0x0800:
		return data ,True
	return data,False

def dosAtt(ip):
	global dos
	flag = False
	for x in dos:
		if ip == x:
			flag = True
			dos[x] += 1
			break
	if flag == False and ip != "192.168.1.254":
		dos[ip] = 1

def main():
	global sock_created
	global sniffer_socket
	if sock_created == False:
		sniffer_socket = socket.socket(socket.PF_PACKET,socket.SOCK_RAW,socket.htons(0x0003))
		sock_created = True

	recv_data = sniffer_socket.recv(2048)

	recv_data,ip_bool = analyze_ether_header(recv_data)

	if(ip_bool):
		recv_data,tcp_udp = analyze_ip_header(recv_data)
	else:
		return
	if(tcp_udp == "tcp"):
		recv_data = analyze_tcp_header(recv_data)
	if(tcp_udp == "udp"):
		recv_data = analyze_udp_header(recv_data)

	#print ("|=================================DATA====================================|")
	#PacketData = ''.join([i if (ord(i) < 128 and ord(i) > 31) else '.' for i in recv_data])
	#print PacketData
	#if "loic" in PacketData:
	#	print '[!] This Connection : ' + src_ip + ' ->>> ' + dst_ip + ' Downloaded LOIC.'
	dosAtt(src_ip)
	dosAtt(dst_ip)
	return

def output():
	global dos
	time.sleep(60)
	os.system("clear")
	x=0
	for ip,num in dos.iteritems():
		if num > 100000:
			print bcolors.FAIL
			sys.stdout.write("\x1b7\x1b[%d;%df%s\x1b8" % (3+x, 100, "Guessing DOS Attack !!!"))
			print bcolors.ENDC
		elif num > 50000:
			print bcolors.WARNING
			sys.stdout.write("\x1b7\x1b[%d;%df%s\x1b8" % (3+x, 100, "UNnormal Traffic !!"))
			print bcolors.ENDC
		sys.stdout.write("\x1b7\x1b[%d;%df%s\x1b8" % (3+x, 60, location(ip)))
		sys.stdout.write("\x1b7\x1b[%d;%df%s\x1b8" % (3+x, 40, ip))
		sys.stdout.write("\x1b7\x1b[%d;%df%s\x1b8" % (3+x, 90, str(num)))
		x += 1
	dos = {}

def location(ip):
	rec = gi.record_by_name(ip)
	if rec:
		s = rec['country_name']
	else:
		s = ""
	return s

def runmain():
	while(True):
		main()

def runoutput():
	while(True):
		output()

try:
	t1 = threading.Thread(target=runmain)
	t2 = threading.Thread(target=runoutput)
	t1.start()
	t2.start()
except:
	print "error in threading"
