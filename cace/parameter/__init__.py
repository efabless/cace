# Copyright 2024 Efabless Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from .parameter_manager import ParameterManager

from .parameter_netgen_lvs import ParameterNetgenLVS
from .parameter_magic_drc import ParameterMagicDRC
from .parameter_magic_area import ParameterMagicArea
from .parameter_magic_antenna_check import ParameterMagicAntennaCheck
from .parameter_ngspice import ParameterNgspice
from .parameter_klayout_drc import ParameterKLayoutDRC
