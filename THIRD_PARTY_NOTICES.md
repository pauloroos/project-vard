# Third-Party Notices

Este projeto inclui código portado/adaptado de projetos de terceiros sob licenças compatíveis.

## Open-LLM-VTuber (MIT)

Os módulos `voz/vard_voz/edge.py` e `voz/vard_voz/piper.py` foram portados/adaptados do projeto
[Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber), especificamente dos arquivos:

- `src/open_llm_vtuber/tts/edge_tts.py`
- `src/open_llm_vtuber/tts/piper_tts.py`

**Copyright (c) Yi-Ting Chiu**

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Python Software Foundation License

O runtime Python embutido é distribuído sob a PSF License Agreement for Python 3.13:

```
1. This LICENSE AGREEMENT is between the Python Software Foundation
("PSF"), and the Individual or Organization ("Licensee") accessing and
otherwise using this software ("Python") in source or binary form and
its associated documentation.

2. Subject to the terms and conditions of this License Agreement, PSF hereby
grants Licensee a nonexclusive, royalty-free, world-wide license to reproduce,
analyze, test, perform and/or display publicly, prepare derivative works,
distribute, and otherwise use Python alone or in any derivative version,
provided, however, that PSF's License Agreement and PSF's notice of copyright,
i.e., "Copyright (c) 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023 Python Software Foundation;
All Rights Reserved" are retained in Python alone or in any derivative version
prepared by Licensee.

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
| comtypes | MIT |
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
| uiautomation | Apache-2.0 |
| uvicorn | BSD-3-Clause |
| watchfiles | MIT |
| websockets | BSD-3-Clause |

Os textos completos das licenças estão disponíveis nos respectivos repositórios ou em https://opensource.org/licenses/.

## Silero VAD e detector web

@ricky0123/vad-web 0.0.31 (ISC), com modelo Silero v5 (MIT).
Origem: https://github.com/ricky0123/vad

```
ISC License

Copyright (c) 2022-present ricky0123

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

---

The file silero_vad.onnx falls under the following license:

---

MIT License

Copyright (c) 2020-present Silero Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```

## ONNX Runtime Web

onnxruntime-web 1.22.0 (MIT). Origem: https://github.com/microsoft/onnxruntime

```
MIT License

Copyright (c) Microsoft Corporation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```

## Kokoro no serviço de voz (opcional)

Instalado só quando você escolhe o Kokoro na aba Voz; nada disto vem no instalador do Vard.

- **kokoro-onnx 0.6.1** (MIT), extra `kokoro` do serviço de voz (`voz/pyproject.toml`).
  Origem: https://github.com/thewh1teagle/kokoro-onnx
- **Modelo Kokoro-82M v1.0** (Apache-2.0), arquivos `kokoro-v1.0.int8.onnx` e `voices-v1.0.bin` baixados pelo
  instalador de vozes (pacote `kokoro`, hash SHA-256 conferido) a partir das releases do kokoro-onnx.
  Origem dos pesos: https://huggingface.co/hexgrad/Kokoro-82M. Texto da licença: https://www.apache.org/licenses/LICENSE-2.0
- Dependências que o kokoro-onnx instala no ambiente do serviço de voz, rodando como processo separado do
  aplicativo: **phonemizer 3.4.0** (GPL-3.0-or-later, https://github.com/bootphon/phonemizer) e
  **espeakng-loader 0.2.4** (MIT, https://github.com/thewh1teagle/espeakng-loader), que traz a biblioteca
  **eSpeak NG** (GPL-3.0-or-later, https://github.com/espeak-ng/espeak-ng) usada para os fonemas; e
  **onnxruntime** (MIT, https://github.com/microsoft/onnxruntime).

```
MIT License

Copyright (c) 2025 github.com/thewh1teagle

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
