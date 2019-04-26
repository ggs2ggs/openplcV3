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

// A simple application that defines the items normally that are provided
// by the glue generator and MATIEC. This allows us to do a simple check
// of the ability to compile everything together, which is useful since
// much of this is only determined when we have a structured text input file.

void config_init__(void)
{}

void config_run__(unsigned long tick)
{}

unsigned long long common_ticktime__ = 50000000ULL; /*ns*/
