# Makefile

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2

all: udp_client udp_server

udp_client: udp_client.c protocol.h
	$(CC) $(CFLAGS) -o udp_client udp_client.c

udp_server: udp_server.c protocol.h
	$(CC) $(CFLAGS) -o udp_server udp_server.c

clean:
	rm -f udp_client udp_server *.o