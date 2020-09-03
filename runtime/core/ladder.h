// Copyright 2015 Thiago Alves
// Copyright 2019 Garret Fick
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http ://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissionsand
// limitations under the License.


// This file is to be used in conjuction with OPLC_Compiler generated code.
// It is the "glue" that holds all parts of the OpenPLC together.
// Thiago Alves, Oct 2015
//-----------------------------------------------------------------------------

#include <cstdint>
#include <mutex>

/** \addtogroup openplc_runtime
 *  @{
 */

// Internal buffers for I/O and memory. These buffers are defined in the
// auto-generated glueVars.cpp file
#define BUFFER_SIZE         1024
/*********************/
/*  IEC Types defs   */
/*********************/

typedef uint8_t  IEC_BOOL;

typedef int8_t    IEC_SINT;
typedef int16_t   IEC_INT;
typedef int32_t   IEC_DINT;
typedef int64_t   IEC_LINT;

typedef uint8_t    IEC_USINT;
typedef uint16_t   IEC_UINT;
typedef uint32_t   IEC_UDINT;
typedef uint64_t   IEC_ULINT;

typedef uint8_t    IEC_BYTE;
typedef uint16_t   IEC_WORD;
typedef uint32_t   IEC_DWORD;
typedef uint64_t   IEC_LWORD;

typedef float    IEC_REAL;
typedef double   IEC_LREAL;

// Booleans
extern IEC_BOOL *bool_input[BUFFER_SIZE][8];
extern IEC_BOOL *bool_output[BUFFER_SIZE][8];

// Bytes
extern IEC_BYTE *byte_input[BUFFER_SIZE];
extern IEC_BYTE *byte_output[BUFFER_SIZE];

// Analog I/O
extern IEC_UINT *int_input[BUFFER_SIZE];
extern IEC_UINT *int_output[BUFFER_SIZE];

// Memory
extern IEC_UINT *int_memory[BUFFER_SIZE];
extern IEC_DINT *dint_memory[BUFFER_SIZE];
extern IEC_LINT *lint_memory[BUFFER_SIZE];

// Special Functions
extern IEC_LINT *special_functions[BUFFER_SIZE];

// lock for the buffer
extern std::mutex bufferLock;

// Common task timer
extern unsigned long long common_ticktime__;

struct GlueVariable;
class GlueVariablesBinding;

//----------------------------------------------------------------------
// FUNCTION PROTOTYPES
//----------------------------------------------------------------------

// MatIEC Compiler
extern "C" {
    void config_run__(unsigned long tick);  
    void config_init__(void);
}
// glueVars.cpp
void glueVars();
void updateTime();

// hardware_layer.cpp
void initializeHardware();
void finalizeHardware();
void updateBuffersIn();
void updateBuffersOut();

// custom_layer.h
void initCustomLayer();
void updateCustomIn();
void updateCustomOut();
extern int ignored_bool_inputs[];
extern int ignored_bool_outputs[];
extern int ignored_int_inputs[];
extern int ignored_int_outputs[];

// main.cpp
bool pinNotPresent(int *ignored_vector, int vector_size, int pinNumber);
extern uint8_t run_openplc;

// server.cpp
typedef std::int16_t (*process_message_fn)(unsigned char *buffer, std::int16_t buffer_size, void* user_data);
void start_server(uint16_t port, volatile bool& run_server, process_message_fn process_message, void* user_data);
void close_socket(int fd);
bool SetSocketBlockingEnabled(int fd, bool blocking);

// interactive_server.cpp
void initialize_logging(int argc, char **argv);
extern time_t start_time;

void bootstrap();

/** @}*/
