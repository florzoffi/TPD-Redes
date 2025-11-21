cmake_minimum_required(VERSION 3.16)
project(tpd_redes C)

set(CMAKE_C_STANDARD 11)

# Place built executables in the repository root
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_SOURCE_DIR})

include_directories(${CMAKE_SOURCE_DIR}/src)

add_executable(server src/server.c)
add_executable(client src/client.c)
