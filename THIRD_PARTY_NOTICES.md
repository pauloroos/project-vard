# Third-Party Notices

Este arquivo lista os componentes de terceiros incluídos no instalador do Vard.

## Python Runtime (embutido)

- **Nome:** CPython 3.13.15 (python-build-standalone)
- **Origem:** https://github.com/astral-sh/python-build-standalone
- **Licença:** Python Software Foundation License Version 2
- **Copyright:** © 2001-2026 Python Software Foundation

```
PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2
--------------------------------------------

1. This LICENSE AGREEMENT is between the Python Software Foundation
("PSF"), and the Individual or Organization ("Licensee") accessing and
otherwise using this software ("Python") in source or binary form and
its associated documentation.

2. Subject to the terms and conditions of this License Agreement, PSF hereby
grants Licensee a nonexclusive, royalty-free, world-wide license to reproduce,
analyze, test, perform and/or display publicly, prepare derivative works,
distribute, and otherwise use Python alone or in any derivative version,
provided, however, that PSF's License Agreement and PSF's notice of copyright,
i.e., "Copyright (c) 2001-2026 Python Software Foundation; All Rights Reserved"
are retained in Python alone or in any derivative version prepared by Licensee.

3. In the event Licensee prepares a derivative work that is based on
or incorporates Python or any part thereof, and wants to make
the derivative work available to others as provided herein, then
Licensee hereby agrees to include in any such work a brief summary of
the changes made to Python.

4. PSF is making Python available to Licensee on an "AS IS"
basis.  PSF MAKES NO REPRESENTATIONS OR WARRANTIES, EXPRESS OR
IMPLIED.  BY WAY OF EXAMPLE, BUT NOT LIMITATION, PSF MAKES NO AND
DISCLAIMS ANY REPRESENTATION OR WARRANTY OF MERCHANTABILITY OR FITNESS
FOR ANY PARTICULAR PURPOSE OR THAT THE USE OF PYTHON WILL NOT
INFRINGE ANY THIRD PARTY RIGHTS.

5. PSF SHALL NOT BE LIABLE TO LICENSEE OR ANY OTHER USERS OF PYTHON
FOR ANY INCIDENTAL, SPECIAL, OR CONSEQUENTIAL DAMAGES OR LOSS AS
A RESULT OF MODIFYING, DISTRIBUTING, OR OTHERWISE USING PYTHON,
OR ANY DERIVATIVE THEREOF, EVEN IF ADVISED OF THE POSSIBILITY THEREOF.

6. This License Agreement will automatically terminate upon a material
breach of its terms and conditions.

7. Nothing in this License Agreement shall be deemed to create any
relationship of agency, partnership, or joint venture between PSF and
Licensee.  This License Agreement does not grant permission to use PSF
trademarks or trade name in a trademark sense to endorse or promote
products or services of Licensee, or any third party.

8. By copying, installing or otherwise using Python, Licensee
agrees to be bound by the terms and conditions of this License
Agreement.
```

## Dependências do Núcleo (incluídas no bundle)

As seguintes bibliotecas são instaladas via `uv pip install --require-hashes` e distribuídas junto com o runtime:

| Pacote | Licença |
|--------|---------|
| annotated-types | MIT |
| anyio | MIT |
| attrs | MIT |
| certifi | MPL-2.0 |
| cffi | MIT |
| click | BSD-3-Clause |
| cryptography | Apache-2.0 / BSD-3-Clause |
| fastapi | MIT |
| h11 | MIT |
| httpcore | BSD-3-Clause |
| httptools | MIT |
| httpx | BSD-3-Clause |
| idna | BSD-3-Clause |
| jsonschema | MIT |
| jsonschema-specifications | MIT |
| markdown | BSD-3-Clause |
| mcp | MIT |
| mss | MIT |
| opentelemetry-api | Apache-2.0 |
| pillow | HPND |
| psutil | BSD-3-Clause |
| pycparser | BSD-3-Clause |
| pydantic | MIT |
| pydantic-core | MIT |
| pyjwt | MIT |
| pystray | MIT |
| python-dotenv | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| pywin32 | PSF |
| pyyaml | MIT |
| referencing | MIT |
| rpds-py | MIT |
| six | MIT |
| sse-starlette | BSD-3-Clause |
| starlette | BSD-3-Clause |
| tomli-w | MIT |
| typing-extensions | PSF |
| uvicorn | BSD-3-Clause |
| watchfiles | MIT |
| websockets | BSD-3-Clause |

Os textos completos das licenças estão disponíveis nos respectivos repositórios ou em https://opensource.org/licenses/.