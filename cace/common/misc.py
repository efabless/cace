# Copyright 2023 Efabless Corporation
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
import os
import re
import typing
import pathlib
import unicodedata
from typing import (
    Any,
    Generator,
    Iterable,
    List,
    TypeVar,
    Optional,
    SupportsFloat,
    Union,
)

# The following code snippet has been adapted under the following license:
#
# Copyright (c) Django Software Foundation and individual contributors.
# All rights reserved.

# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:

#     1. Redistributions of source code must retain the above copyright notice,
#        this list of conditions and the following disclaimer.

#     2. Redistributions in binary form must reproduce the above copyright
#        notice, this list of conditions and the following disclaimer in the
#        documentation and/or other materials provided with the distribution.

#     3. Neither the name of Django nor the names of its contributors may be used
#        to endorse or promote products derived from this software without
#        specific prior written permission.


# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
def slugify(value: str, lower: bool = False) -> str:
    """
    :param value: Input string
    :returns: The input string converted to lower case, with all characters
        except alphanumerics, underscores and hyphens removed, and spaces and\
        dots converted into hyphens.

        Leading and trailing whitespace is stripped.
    """
    if lower:
        value = value.lower()
    value = (
        unicodedata.normalize('NFKD', value)
        .encode('ascii', 'ignore')
        .decode('ascii')
    )
    value = re.sub(r'[^\w\s\-\.]', '', value).strip().lower()
    return re.sub(r'[\s\.]+', '-', value)


def protected(method):
    """A decorator to indicate protected methods.

    It dynamically adds a statement to the effect in the docstring as well
    as setting an attribute, ``protected``, to ``True``, but has no other effects.

    :param f: Method to mark as protected
    """
    if method.__doc__ is None:
        method.__doc__ = ''
    method.__doc__ = '**protected**\n' + method.__doc__

    setattr(method, 'protected', True)
    return method


final = typing.final
final.__doc__ = """A decorator to indicate final methods and final classes.

    Use this decorator to indicate to type checkers that the decorated
    method cannot be overridden, and decorated class cannot be subclassed.
    For example:


    .. code-block:: python

       class Base:
           @final
           def done(self) -> None:
               ...
       class Sub(Base):
           def done(self) -> None:  # Error reported by type checker
                 ...

       @final
       class Leaf:
           ...
       class Other(Leaf):  # Error reported by type checker
           ...

    There is no runtime checking of these properties.
"""


def mkdirp(path: typing.Union[str, os.PathLike]):
    """
    Attempts to create a directory and all of its parents.

    Does not fail if the directory already exists, however, it does fail
    if it is unable to create any of the components and/or if the path
    already exists as a file.

    :param path: A filesystem path for the directory
    """
    return pathlib.Path(path).mkdir(parents=True, exist_ok=True)
