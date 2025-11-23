CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2

all: tcp_client tcp_server

tcp_client: tcp_client.c protocol_tcp.h
	$(CC) $(CFLAGS) -o tcp_client tcp_client.c

tcp_server: tcp_server.c protocol_tcp.h
	$(CC) $(CFLAGS) -o tcp_server tcp_server.c

clean:
	rm -f tcp_client tcp_server delay.csv
