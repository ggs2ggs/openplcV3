// Copyright 2015 Thiago Alves
// Copyright 2019 Smarter Grid Solutions
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


// This file has all the MODBUS/TCP functions supported by the OpenPLC. If any
// other function is to be added to the project, it must be added here
// Thiago Alves, Dec 2015
//-----------------------------------------------------------------------------

#include <array>
#include <functional>
#include <fstream>
#include <memory>
#include <string>

#include <ini.h>
#include <spdlog/spdlog.h>

#include "slave.h"
#include "indexed_strategy.h"
#include "mb_util.h"
#include  "../ladder.h"
#include "../glue.h"
#include "../ini_util.h"

/** \addtogroup openplc_runtime
 *  @{
 */
#define MAX_COILS                       8192

#define MB_FC_NONE                      0
#define MB_FC_READ_COILS                1
#define MB_FC_READ_INPUTS               2
#define MB_FC_READ_HOLDING_REGISTERS    3
#define MB_FC_READ_INPUT_REGISTERS      4
#define MB_FC_WRITE_COIL                5
#define MB_FC_WRITE_REGISTER            6
#define MB_FC_WRITE_MULTIPLE_COILS      15
#define MB_FC_WRITE_MULTIPLE_REGISTERS  16
#define MB_FC_ERROR                     255

#define ERR_NONE                        0
#define ERR_ILLEGAL_FUNCTION            1
#define ERR_ILLEGAL_DATA_ADDRESS        2
#define ERR_ILLEGAL_DATA_VALUE          3
#define ERR_SLAVE_DEVICE_FAILURE        4
#define ERR_SLAVE_DEVICE_BUSY           6

#define bit_read(value, bit) (((value) >> (bit)) & 0x01)
#define bit_set(value, bit) ((value) |= (1UL << (bit)))
#define bit_clear(value, bit) ((value) &= ~(1UL << (bit)))
#define bit_write(value, bit, bitvalue) (bitvalue ? bit_set(value, bit) : bit_clear(value, bit))


using namespace std;

/// \brief Response to a Modbus Error
/// \param *buffer
/// \param mb_error
int modbus_error(unsigned char *buffer, int mb_error)
{
	buffer[4] = 0;
	buffer[5] = 3;
	buffer[7] = buffer[7] | 0x80; //set the highest bit
	buffer[8] = mb_error;
	return 9;
}

inline int read_sizes(unsigned char* buffer, int buffer_size, int16_t& start,
               int16_t& num_items) {
	// This request must have at least 12 bytes. If it doesn't, it's a corrupted message
	if (buffer_size < 12)
	{
		return modbus_error(buffer, ERR_ILLEGAL_DATA_VALUE);
	}

	start = mb_to_word(buffer[8], buffer[9]);
	num_items = mb_to_word(buffer[10], buffer[11]);

	return 0;
}

inline int read_sized_bytes(unsigned char* buffer, int buffer_size, int16_t& start,
                   int16_t& num_coils, int16_t& num_bytes) {

	int ret = read_sizes(buffer, buffer_size, start, num_coils);

	// Calculate the size of the message in bytes - they are packed into
	// 8 coils per byte.
	num_bytes = num_coils / 8;
	// "Round up" since the above is integer division and truncates any
	// extra items beyond 8.
	if(num_bytes * 8 < num_coils) {
        num_bytes++;
    }

	if (num_bytes > 255) {
		return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
	}

	return 0;
}

/// @brief Implementation of Modbus/TCP Read Coils
/// @param buffer
/// @param buffer_size
int read_coils(unsigned char *buffer, int buffer_size, IndexedStrategy* strategy)
{
	int16_t start;
	int16_t coil_data_length;
	int16_t byte_data_length;
	int ret = read_sized_bytes(buffer, buffer_size, start, coil_data_length, byte_data_length);
	if (ret != 0) {
		return ret;
	}

	// Preparing response
	buffer[4] = mb_high_byte(byte_data_length + 3);
    // Number of bytes after this one
	buffer[5] = mb_low_byte(byte_data_length + 3);
    // Number of bytes of data
	buffer[8] = byte_data_length;

    modbus_errno err = strategy->ReadCoils(start, coil_data_length, reinterpret_cast<uint8_t*>(buffer + 9));
    if (err) {
        return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
    }

    return byte_data_length + 9;
}

/// @brief Implementation of Modbus/TCP Read Discrete Inputs
/// @param buffer
/// @param buffer_size
int read_discrete_inputs(unsigned char *buffer, int buffer_size, IndexedStrategy* strategy)
{
	int16_t start;
	int16_t input_data_length;
	int16_t byte_data_length;
	int ret = read_sized_bytes(buffer, buffer_size, start, input_data_length, byte_data_length);
	if (ret != 0) {
		return ret;
	}

	//Preparing response
	buffer[4] = mb_high_byte(byte_data_length + 3);
	buffer[5] = mb_low_byte(byte_data_length + 3); //Number of bytes after this one
	buffer[8] = byte_data_length;     //Number of bytes of data

    modbus_errno err = strategy->ReadDiscreteInputs(start, input_data_length, reinterpret_cast<uint8_t*>(buffer + 9));
    if (err) {
        return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
    }

    return byte_data_length + 9;
}

/// @brief Implementation of Modbus/TCP Read Holding Registers
/// @param *buffer
/// @param bufferSize
int read_holding_registers(unsigned char *buffer, int buffer_size, IndexedStrategy* strategy)
{
	int16_t start;
	int16_t num_registers;
	int ret = read_sizes(buffer, buffer_size, start, num_registers);
	if (ret != 0) {
		return ret;
	}

	int16_t byte_data_length = num_registers * 2;

	//preparing response
	buffer[4] = mb_high_byte(byte_data_length + 3);
	buffer[5] = mb_low_byte(byte_data_length + 3); //Number of bytes after this one
	buffer[8] = byte_data_length;     //Number of bytes of data

	modbus_errno err = strategy->ReadHoldingRegisters(start, num_registers, reinterpret_cast<uint8_t*>(buffer + 9));
    if (err) {
        return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
    }

    return byte_data_length + 9;
}

/// @brief Implementation of Modbus/TCP Read Input Registers
/// @param *buffer
/// @param bufferSize
int read_input_registers(unsigned char *buffer, int buffer_size, IndexedStrategy* strategy)
{
	int16_t start;
	int16_t num_registers;
	int ret = read_sizes(buffer, buffer_size, start, num_registers);
	if (ret != 0) {
		return ret;
	}

	int16_t byte_data_length = num_registers * 2;

	//preparing response
	buffer[4] = mb_high_byte(byte_data_length + 3);
	buffer[5] = mb_low_byte(byte_data_length + 3); //Number of bytes after this one
	buffer[8] = byte_data_length;     //Number of bytes of data

	modbus_errno err = strategy->ReadInputRegisters(start, num_registers, reinterpret_cast<uint8_t*>(buffer + 9));
    if (err) {
        return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
    }

    return byte_data_length + 9;
}

int write_coil(unsigned char* buffer, int buffer_size, IndexedStrategy* strategy)
{
	int16_t start = mb_to_word(buffer[8], buffer[9]);
	bool value = mb_to_word(buffer[10], buffer[11]) != 0;

	modbus_errno err = strategy->WriteCoil(start, value);
	if (err) {
        return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
    }

	buffer[4] = 0;
	//Number of bytes after this one.
	buffer[5] = 6;
	return 12;
}

int write_holding_register(unsigned char* buffer, int buffer_size, IndexedStrategy* strategy)
{
	int16_t start = mb_to_word(buffer[8], buffer[9]);

	modbus_errno err = strategy->WriteHoldingRegister(start, buffer + 9, 2);
	if (err) {
        return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
    }

	buffer[4] = 0;
	//Number of bytes after this one.
	buffer[5] = 6;
	return 12;
}

int write_multiple_coils(unsigned char* buffer, int buffer_size, IndexedStrategy* strategy)
{
	int16_t start;
	int16_t input_data_length;
	int16_t byte_data_length;
	int ret = read_sized_bytes(buffer, buffer_size, start, input_data_length, byte_data_length);
	if (ret != 0) {
		return ret;
	}

	// Check that we have enough bytes
	if (buffer_size < (byte_data_length + 13) || buffer[12] != byte_data_length) {
		return modbus_error(buffer, ERR_ILLEGAL_DATA_VALUE);
	}

	modbus_errno err = strategy->WriteMultipleCoils(start, input_data_length, buffer + 13);
	if (err) {
        return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
    }

	//preparing response
	buffer[4] = 0;
	buffer[5] = 6; //Number of bytes after this one.
	return 12;
}

int write_multiple_registers(unsigned char* buffer, int buffer_size, IndexedStrategy* strategy)
{
	int16_t start;
	int16_t num_registers;
	int ret = read_sizes(buffer, buffer_size, start, num_registers);
	if (ret != 0) {
		return ret;
	}

	// Check that we have enough bytes
	if (buffer_size < (num_registers * 2 + 13) || buffer[12] != num_registers * 2) {
		return modbus_error(buffer, ERR_ILLEGAL_DATA_VALUE);
	}

	modbus_errno err = strategy->WriteHoldingRegisters(start, num_registers, buffer + 13);
	if (err) {
        return modbus_error(buffer, ERR_ILLEGAL_DATA_ADDRESS);
    }

	//preparing response
	buffer[4] = 0;
	buffer[5] = 6; //Number of bytes after this one.
	return 12;
}

/// Parse and process the client request and write back the response for it.
/// @param buffer
/// @param buffer_size
/// @param user_data The mapping strategy.
/// @return size of the response message in bytes
int process_modbus_message(unsigned char *buffer, int buffer_size, void* user_data)
{
    auto strategy = reinterpret_cast<IndexedStrategy*>(user_data);
	int message_length = 0;

	//check if the message is long enough
	if (buffer_size < 8)
	{
		message_length = modbus_error(buffer, ERR_ILLEGAL_FUNCTION);
	}

	//****************** Read Coils **********************
	else if(buffer[7] == MB_FC_READ_COILS)
	{
		message_length = read_coils(buffer, buffer_size, strategy);
	}

	//*************** Read Discrete Inputs ***************
	else if(buffer[7] == MB_FC_READ_INPUTS)
	{
		message_length = read_discrete_inputs(buffer, buffer_size, strategy);
	}

	//****************** Read Holding Registers ******************
	else if(buffer[7] == MB_FC_READ_HOLDING_REGISTERS)
	{
		message_length = read_holding_registers(buffer, buffer_size, strategy);
	}

	//****************** Read Input Registers ******************
	else if(buffer[7] == MB_FC_READ_INPUT_REGISTERS)
	{
		message_length = read_input_registers(buffer, buffer_size, strategy);
	}

	//****************** Write Coil **********************
	else if(buffer[7] == MB_FC_WRITE_COIL)
	{
		message_length = write_coil(buffer, buffer_size, strategy);
	}

	//****************** Write Register ******************
	else if(buffer[7] == MB_FC_WRITE_REGISTER)
	{
		message_length = write_holding_register(buffer, buffer_size, strategy);
	}

	//****************** Write Multiple Coils **********************
	else if(buffer[7] == MB_FC_WRITE_MULTIPLE_COILS)
	{
		message_length = write_multiple_coils(buffer, buffer_size, strategy);
	}

	//****************** Write Multiple Registers ******************
	else if(buffer[7] == MB_FC_WRITE_MULTIPLE_REGISTERS)
	{
		message_length = write_multiple_registers(buffer, buffer_size, strategy);
	}

	//****************** Function Code Error ******************
	else
	{
		message_length = modbus_error(buffer, ERR_ILLEGAL_FUNCTION);
	}

	return message_length;
}


/// Container for reading in configuration from the config.ini
/// This is populated with values from the config file.
struct ModbusSlaveConfig {
    ModbusSlaveConfig() :
        address("127.0.0.1"),
        port(502),
        // The sizes and offsets here are
        // to match the original modbus implementation
        bits_start(0),
        bits_size(8192),
        input_bits_start(0),
        input_bits_size(8192),
        registers_start(0),
        registers_size(8192),
        input_registers_start(0),
        input_registers_size(1024)
    {}

    string address;
    uint16_t port;

    uint16_t bits_start;
    uint16_t bits_size;

    uint16_t input_bits_start;
    uint16_t input_bits_size;

    uint16_t registers_start;
    uint16_t registers_size;

    uint16_t input_registers_start;
    uint16_t input_registers_size;

    uint8_t num_connections;
};

int modbus_slave_cfg_handler(void* user_data, const char* section,
                            const char* name, const char* value) {
    if (strcmp("modbuslave", section) != 0) {
        return 0;
    }

    auto config = reinterpret_cast<ModbusSlaveConfig*>(user_data);

    if (strcmp(name, "port") == 0) {
        config->port = atoi(value);
    } else if (strcmp(name, "address") == 0) {
        config->address = value;
    } else if (strcmp(name, "enabled") == 0) {
        // Nothing to do here - we already know this is enabled
    } else {
        spdlog::warn("Unknown configuration item {}", name);
        return -1;
    }

    return 0;
}

int8_t modbus_slave_run(std::unique_ptr<std::istream, std::function<void(std::istream*)>>& cfg_stream,
                        const char* cfg_overrides,
                        const GlueVariablesBinding& bindings,
                        volatile bool& run) {
    ModbusSlaveConfig config;

    ini_parse_stream(istream_fgets, cfg_stream.get(), modbus_slave_cfg_handler, &config);

    cfg_stream.reset(nullptr);

    IndexedStrategy strategy(bindings);

	spdlog::info("Starting modbus slave on port {}", config.port);
    startServer(config.port, run, &process_modbus_message, &strategy);

    return 0;
}

void modbus_slave_service_run(const GlueVariablesBinding& binding,
                              volatile bool& run, const char* config) {

    unique_ptr<istream, function<void(istream*)>> cfg_stream(new ifstream("../etc/config.ini"), [](istream* s)
        {
            reinterpret_cast<ifstream*>(s)->close();
            delete s;
        });

    modbus_slave_run(cfg_stream, config, binding, run);
}

/** @}*/