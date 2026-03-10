# Execution Service 架构设计

> 方案 D: 混合架构 - 两层工具 + Docker 后端 + Skill 可选编排

## 1. 概述

### 1.1 目标

为 AcademiaGPT v2 添加以下能力：
- **LaTeX 编译**: 支持 pdfLaTeX 和 XeLaTeX，直接编译 LLM 生成的 LaTeX 代码
- **Python 绘图**: 使用 Matplotlib/Seaborn 生成学术图表
- **流程图生成**: 使用 Mermaid 生成架构图、流程图
- **AI 生图**: 调用 Kling/DALL-E API 生成插图

### 1.2 设计原则

1. **与现有架构无缝集成** - 复用 SandboxMiddleware 注入机制
2. **抽象接口预留扩展** - 便于未来切换到微服务架构
3. **安全第一** - Docker 容器隔离 + 代码安全检查
4. **渐进式实现** - 各模块独立可测试

### 1.3 整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LangGraph Agent                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              Semantic Tools Layer (Tools 直接可用)           │   │
│   │                                                              │   │
│   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │   │
│   │  │compile_latex │ │ plot_chart   │ │ create_diagram       │ │   │
│   │  │              │ │              │ │ (mermaid/graphviz)   │ │   │
│   │  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘ │   │
│   │         │                │                    │             │   │
│   │  ┌──────────────┐        │                    │             │   │
│   │  │generate_image│ ◄──────┘                    │             │   │
│   │  │(Kling/DALL-E)│                            │             │   │
│   │  └──────┬───────┘                            │             │   │
│   │         │                                    │             │   │
│   └─────────┼────────────────────────────────────┼─────────────┘   │
│             │                                    │                  │
│   ┌─────────▼────────────────────────────────────▼──────────────┐  │
│   │              ExecutionService (抽象层)                       │  │
│   │                                                              │  │
│   │  interface:                                                  │  │
│   │    - execute(request: ExecutionRequest) -> ExecutionResult  │  │
│   │    - health_check() -> dict                                 │  │
│   └──────────────────────────┬───────────────────────────────────┘  │
│                              │                                       │
│   ┌──────────────────────────▼───────────────────────────────────┐  │
│   │              DockerExecutionService (实现)                    │  │
│   │                                                              │  │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│  │
│   │  │LaTeXProvider│ │PythonProvider│ │DiagramProvider         ││  │
│   │  └─────────────┘ └─────────────┘ └─────────────────────────┘│  │
│   │  ┌─────────────────────────────────────────────────────────┐│  │
│   │  │ImageProvider (AI: Kling/DALL-E, 不用Docker,用API)       ││  │
│   │  └─────────────────────────────────────────────────────────┘│  │
│   │                                                              │  │
│   │  ┌─────────────────────────────────────────────────────────┐│  │
│   │  │              ContainerPool (可选优化)                    ││  │
│   │  │  - 预热容器池                                            ││  │
│   │  │  - 资源监控                                              ││  │
│   │  │  - 自动扩缩                                              ││  │
│   │  └─────────────────────────────────────────────────────────┘│  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │              Optional: High-level Skills                      │  │
│   │                                                              │  │
│   │  LaTeXPaperSkill:     LLM 输出 LaTeX → 编译 → 返回 PDF       │  │
│   │  ImageGenerationSkill: 分析文本 → 选择方式 → 生成图片        │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. 文件结构

```
backend/src/
├── execution/                          # NEW: 统一执行服务
│   ├── __init__.py
│   ├── types.py                        # 数据类型
│   ├── base.py                         # 抽象接口
│   ├── service.py                      # DockerExecutionService
│   ├── providers/                      # 专用执行器
│   │   ├── __init__.py
│   │   ├── base.py                     # BaseProvider
│   │   ├── latex.py                    # LaTeX 编译
│   │   ├── python_viz.py               # Python 绘图
│   │   ├── diagram.py                  # Mermaid/Graphviz
│   │   └── ai_image.py                 # AI 生图 (API调用, 不用Docker)
│   ├── docker/                         # Docker 相关
│   │   ├── __init__.py
│   │   ├── client.py                   # Docker 客户端封装
│   │   ├── pool.py                     # 容器池 (可选)
│   │   └── images.py                   # 镜像管理
│   └── security/                       # 安全检查
│       ├── __init__.py
│       ├── latex_sanitizer.py          # LaTeX 安全检查
│       └── python_sanitizer.py         # Python AST 安全检查
│
├── tools/
│   └── execution/                      # NEW: 执行工具
│       ├── __init__.py
│       ├── compile_latex.py
│       ├── plot_chart.py
│       ├── create_diagram.py
│       └── generate_image.py
│
├── skills/
│   └── implementations/
│       └── paper_writing/              # NEW: 论文写作相关 Skill
│           ├── __init__.py
│           ├── latex_writer.py         # LLaMA 论文 Skill
│           └── image_orchestrator.py   # 图片生成编排 Skill
│
└── sandbox/                            # 保持不变
    └── ...

docker/
├── images/                             # NEW: Docker 镜像
│   ├── texlive/
│   │   └── Dockerfile                  # TeXLive 2024
│   ├── python-viz/
│   │   └── Dockerfile                  # Python + Matplotlib + Seaborn
│   └── diagram/
│       └── Dockerfile                  # Mermaid CLI + Graphviz
└── docker-compose.yml                  # 更新
```

## 3. 核心类型定义

### 3.1 执行类型和结果

```python
# src/execution/types.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
from datetime import datetime


class ExecutionType(Enum):
    """执行类型"""
    LATEX_COMPILE = "latex_compile"
    PYTHON_PLOT = "python_plot"
    MERMAID_DIAGRAM = "mermaid_diagram"
    AI_IMAGE = "ai_image"


class ExecutionStatus(Enum):
    """执行状态"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SECURITY_VIOLATION = "security_violation"


class CompilerType(Enum):
    """LaTeX 编译器类型"""
    PDFLATEX = "pdflatex"
    XELATEX = "xelatex"


class ImageProvider(Enum):
    """AI 图片生成提供商"""
    KLING = "kling"
    DALLE = "dalle"
    STABLE_DIFFUSION = "sd"  # 本地部署 (未来)


@dataclass
class ExecutionRequest:
    """执行请求"""
    execution_type: ExecutionType
    content: str                              # 源代码或提示词
    options: dict[str, Any] = field(default_factory=dict)
    timeout: int = 120
    workspace_id: Optional[str] = None
    thread_id: Optional[str] = None
    output_filename: Optional[str] = None

    # 类型特定选项
    # LaTeX: compiler, bibliography, template
    # Python: style, figure_size, dpi
    # Mermaid: theme, format
    # AI Image: provider, aspect_ratio, style


@dataclass
class ProviderResult:
    """Provider 执行结果 (内部使用)"""
    success: bool
    output_files: list[str] = field(default_factory=list)  # 相对路径
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    logs: Optional[str] = None


@dataclass
class ExecutionResult:
    """执行结果 (返回给 Tool)"""
    status: ExecutionStatus
    sandbox_path: Optional[str] = None       # sandbox 虚拟路径
    artifact_id: Optional[str] = None        # 持久化后的 artifact ID
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    # 调试信息
    logs: Optional[str] = None
    source_code: Optional[str] = None

    def to_tool_output(self) -> str:
        """转换为 Tool 返回字符串"""
        if self.status == ExecutionStatus.SUCCESS:
            return f"Success. Output: {self.sandbox_path}"
        return f"Failed: {self.error_message}"
```

### 3.2 抽象接口

```python
# src/execution/base.py

from abc import ABC, abstractmethod
from .types import ExecutionRequest, ExecutionResult


class ExecutionService(ABC):
    """执行服务抽象接口 - 预留未来扩展"""

    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """执行任务"""
        pass

    @abstractmethod
    async def health_check(self) -> dict:
        """健康检查"""
        pass


class ExecutionProvider(ABC):
    """执行器基类"""

    @property
    @abstractmethod
    def execution_type(self) -> str:
        """支持的执行类型"""
        pass

    @property
    @abstractmethod
    def docker_image(self) -> str:
        """Docker 镜像名称 (None 表示不需要 Docker)"""
        pass

    @abstractmethod
    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict,
        docker_client: Optional["DockerClient"] = None,
    ) -> "ProviderResult":
        """
        执行具体任务

        Args:
            content: 源代码或提示词
            work_dir: 工作目录 (宿主机路径)
            options: 执行选项
            docker_client: Docker 客户端 (如果需要容器)

        Returns:
            ProviderResult
        """
        pass
```

## 4. Docker 执行服务实现

### 4.1 Docker 客户端封装

```python
# src/execution/docker/client.py

import asyncio
import logging
from pathlib import Path
from typing import Optional

import docker
from docker.models.containers import Container

from ..types import ExecutionRequest, ProviderResult

logger = logging.getLogger(__name__)


class DockerExecutionError(Exception):
    """Docker 执行错误"""
    pass


class DockerClient:
    """Docker 客户端封装"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    async def run_container(
        self,
        image: str,
        command: list[str],
        volumes: dict[str, dict],
        timeout: int = 120,
        memory: str = "1g",
        cpu_quota: int = 100000,  # 1 CPU
        remove: bool = True,
    ) -> tuple[int, str, str]:
        """
        运行容器并返回结果

        Returns:
            (exit_code, stdout, stderr)
        """
        loop = asyncio.get_event_loop()

        def _run():
            try:
                container = self.client.containers.run(
                    image=image,
                    command=command,
                    volumes=volumes,
                    mem_limit=memory,
                    cpu_quota=cpu_quota,
                    remove=False,
                    detach=False,
                    stdout=True,
                    stderr=True,
                    network_disabled=True,  # 禁用网络 (安全)
                )
                # container.run returns bytes when not detached
                output = container or b""
                return 0, output.decode("utf-8", errors="replace"), ""
            except docker.errors.ContainerError as e:
                return e.exit_status, e.stderr.decode() if e.stderr else "", ""
            except docker.errors.ImageNotFound:
                raise DockerExecutionError(f"Image not found: {image}")
            except docker.errors.APIError as e:
                raise DockerExecutionError(f"Docker API error: {e}")

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, _run),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            raise DockerExecutionError(f"Container timeout after {timeout}s")

    async def ensure_image(self, image: str) -> bool:
        """确保镜像存在，不存在则拉取"""
        try:
            self.client.images.get(image)
            return True
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling image: {image}")
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.client.images.pull(image)
            )
            return True

    def build_volume_mapping(
        self,
        host_dir: str,
        container_dir: str = "/workspace",
        mode: str = "rw"
    ) -> dict:
        """构建卷映射"""
        return {
            host_dir: {"bind": container_dir, "mode": mode}
        }
```

### 4.2 主执行服务

```python
# src/execution/service.py

import logging
import time
from pathlib import Path
from typing import Optional

from .base import ExecutionService
from .types import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
)
from .docker.client import DockerClient, DockerExecutionError
from .providers import (
    LaTeXProvider,
    PythonVizProvider,
    DiagramProvider,
    AIImageProvider,
)

logger = logging.getLogger(__name__)


class DockerExecutionService(ExecutionService):
    """Docker 后端执行服务"""

    PROVIDER_MAP = {
        ExecutionType.LATEX_COMPILE: LaTeXProvider,
        ExecutionType.PYTHON_PLOT: PythonVizProvider,
        ExecutionType.MERMAID_DIAGRAM: DiagramProvider,
        ExecutionType.AI_IMAGE: AIImageProvider,  # 不用 Docker
    }

    def __init__(
        self,
        sandbox_base_dir: str,
        docker_config: dict | None = None,
    ):
        self.sandbox_base_dir = Path(sandbox_base_dir)
        self.docker_client = DockerClient(docker_config)
        self._providers: dict[ExecutionType, Any] = {}

    def _get_provider(self, exec_type: ExecutionType):
        """获取或创建 Provider 实例"""
        if exec_type not in self._providers:
            provider_cls = self.PROVIDER_MAP.get(exec_type)
            if not provider_cls:
                raise ValueError(f"Unsupported execution type: {exec_type}")
            self._providers[exec_type] = provider_cls()
        return self._providers[exec_type]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """执行任务"""
        start_time = time.time()

        try:
            provider = self._get_provider(request.execution_type)

            # 准备工作目录
            work_dir = self._prepare_work_dir(request)
            output_dir = work_dir / "output"
            output_dir.mkdir(exist_ok=True)

            # 执行
            if provider.docker_image:
                # 需要 Docker 的执行
                result = await self._execute_in_docker(
                    provider, request, str(work_dir)
                )
            else:
                # 不需要 Docker (如 API 调用)
                result = await provider.execute(
                    content=request.content,
                    work_dir=str(work_dir),
                    options=request.options,
                )

            # 处理结果
            execution_time_ms = int((time.time() - start_time) * 1000)

            if result.success and result.output_files:
                # 转换为 sandbox 虚拟路径
                sandbox_path = self._to_sandbox_path(
                    work_dir / result.output_files[0],
                    request.thread_id
                )

                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    sandbox_path=sandbox_path,
                    execution_time_ms=execution_time_ms,
                    metadata=result.metadata,
                    logs=result.logs,
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error_message=result.error_message or "Execution failed",
                    execution_time_ms=execution_time_ms,
                    logs=result.logs,
                )

        except DockerExecutionError as e:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
            )

        except asyncio.TimeoutError:
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                error_message=f"Execution timeout after {request.timeout}s",
                execution_time_ms=request.timeout * 1000,
            )

    async def _execute_in_docker(
        self,
        provider,
        request: ExecutionRequest,
        work_dir: str,
    ) -> "ProviderResult":
        """在 Docker 容器中执行"""

        # 确保镜像存在
        await self.docker_client.ensure_image(provider.docker_image)

        # 构建卷映射
        volumes = self.docker_client.build_volume_mapping(
            host_dir=work_dir,
            container_dir="/workspace",
        )

        # 让 provider 构建命令
        command = provider.build_command(request.content, request.options)

        # 运行容器
        exit_code, stdout, stderr = await self.docker_client.run_container(
            image=provider.docker_image,
            command=command,
            volumes=volumes,
            timeout=request.timeout,
        )

        # 让 provider 处理结果
        return await provider.process_result(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            work_dir=work_dir,
            options=request.options,
        )

    def _prepare_work_dir(self, request: ExecutionRequest) -> Path:
        """准备工作目录"""
        thread_id = request.thread_id or "default"
        work_dir = (
            self.sandbox_base_dir
            / thread_id
            / "execution"
            / request.execution_type.value
            / datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    def _to_sandbox_path(self, physical_path: Path, thread_id: str) -> str:
        """转换为 sandbox 虚拟路径"""
        # 将物理路径映射为 /mnt/user-data/... 虚拟路径
        relative = physical_path.relative_to(self.sandbox_base_dir / thread_id)
        return f"/mnt/user-data/{relative}"

    async def health_check(self) -> dict:
        """健康检查"""
        try:
            self.docker_client.client.ping()
            return {
                "status": "healthy",
                "docker": "connected",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }
```

## 5. Provider 实现

### 5.1 LaTeX Provider

```python
# src/execution/providers/latex.py

import logging
import re
from pathlib import Path
from typing import Optional

from .base import ExecutionProvider
from ..types import ProviderResult, CompilerType
from ..security.latex_sanitizer import sanitize_latex

logger = logging.getLogger(__name__)


class LaTeXProvider(ExecutionProvider):
    """LaTeX 编译 Provider"""

    execution_type = "latex_compile"
    docker_image = "academiagpt/texlive:2024"

    # 危险命令黑名单
    DANGEROUS_COMMANDS = [
        r"\\write18",
        r"\\immediate\\write",
        r"\\input{|",
        r"\\includegraphics.*\|",
        r"\\shell-escape",
        r"\\catcode",
        r"\\endlinechar",
    ]

    def build_command(self, content: str, options: dict) -> list[str]:
        """构建 Docker 执行命令"""
        compiler = options.get("compiler", "xelatex")

        # 写入源文件
        source_path = Path("/workspace/main.tex")
        write_cmd = f"cat > {source_path} << 'EOF_LATEX'\n{content}\nEOF_LATEX\n"

        # 编译命令
        compile_cmd = self._build_compile_command(compiler, options)

        # 完整命令
        return ["sh", "-c", f"{write_cmd} && {compile_cmd}"]

    def _build_compile_command(self, compiler: str, options: dict) -> str:
        """构建编译命令链"""
        has_bib = options.get("bibliography") is not None
        filename = "main"

        if has_bib:
            # LaTeX -> BibTeX -> LaTeX -> LaTeX
            return (
                f"{compiler} -no-shell-escape -interaction=nonstopmode {filename}.tex && "
                f"bibtex {filename} && "
                f"{compiler} -no-shell-escape -interaction=nonstopmode {filename}.tex && "
                f"{compiler} -no-shell-escape -interaction=nonstopmode {filename}.tex"
            )
        else:
            # 最多编译 3 次处理交叉引用
            compile_once = f"{compiler} -no-shell-escape -interaction=nonstopmode {filename}.tex"
            return f"{compile_once} && {compile_once} && {compile_once}"

    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict,
        docker_client=None,
    ) -> ProviderResult:
        """由 DockerExecutionService 调用，这里只做安全检查"""

        # 安全检查
        is_safe, error = sanitize_latex(content)
        if not is_safe:
            return ProviderResult(
                success=False,
                error_message=f"Security violation: {error}",
            )

        # 实际执行在 Docker 中，由 service 层处理
        raise NotImplementedError("Use DockerExecutionService.execute instead")

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict,
    ) -> ProviderResult:
        """处理容器执行结果"""
        work_path = Path(work_dir)
        pdf_path = work_path / "main.pdf"

        if exit_code == 0 and pdf_path.exists():
            return ProviderResult(
                success=True,
                output_files=["output/main.pdf"],
                metadata={
                    "page_count": self._count_pages(pdf_path),
                    "file_size": pdf_path.stat().st_size,
                },
                logs=stdout[-2000:] if len(stdout) > 2000 else stdout,
            )
        else:
            error = self._extract_error(stdout + stderr)
            return ProviderResult(
                success=False,
                error_message=error,
                logs=stdout[-2000:] if len(stdout) > 2000 else stdout,
            )

    def _extract_error(self, log: str) -> str:
        """从日志提取错误信息"""
        patterns = [
            r"! LaTeX Error: ([^\n]+)",
            r"! File `(.+?)' not found",
            r"! Undefined control sequence",
            r"! (.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, log)
            if match:
                return match.group(0)[:200]
        return "Unknown LaTeX compilation error"

    def _count_pages(self, pdf_path: Path) -> int:
        """获取 PDF 页数"""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0
```

### 5.2 Python 可视化 Provider

```python
# src/execution/providers/python_viz.py

import logging
from pathlib import Path

from .base import ExecutionProvider
from ..types import ProviderResult
from ..security.python_sanitizer import sanitize_python_code

logger = logging.getLogger(__name__)


class PythonVizProvider(ExecutionProvider):
    """Python 数据可视化 Provider"""

    execution_type = "python_plot"
    docker_image = "academiagpt/python-viz:1.0"

    # 允许的导入
    ALLOWED_IMPORTS = {
        "numpy", "np",
        "matplotlib", "matplotlib.pyplot", "plt",
        "matplotlib.patches", "matplotlib.lines",
        "pandas", "pd",
        "scipy", "scipy.stats",
        "seaborn", "sns",
        "math",
    }

    def build_command(self, content: str, options: dict) -> list[str]:
        """构建执行命令"""
        # 安全的字体配置前缀
        font_config = '''
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False
'''

        # 输出路径配置
        output_path = options.get("output_path", "/workspace/output/chart.png")
        dpi = options.get("dpi", 200)

        # 包装代码
        wrapped_code = f'''
{font_config}

# User code
{content}

# Ensure output
import os
os.makedirs('/workspace/output', exist_ok=True)
'''

        # 写入并执行
        return [
            "python", "-c",
            wrapped_code
        ]

    async def execute(self, content: str, work_dir: str, options: dict, docker_client=None) -> ProviderResult:
        raise NotImplementedError("Use DockerExecutionService.execute instead")

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict,
    ) -> ProviderResult:
        """处理执行结果"""
        work_path = Path(work_dir)
        output_dir = work_path / "output"

        # 查找生成的图片
        image_files = list(output_dir.glob("*.png")) + list(output_dir.glob("*.svg"))

        if exit_code == 0 and image_files:
            return ProviderResult(
                success=True,
                output_files=[f"output/{f.name}" for f in image_files],
                metadata={
                    "format": options.get("format", "png"),
                },
                logs=stdout,
            )
        else:
            return ProviderResult(
                success=False,
                error_message=stderr or "Python execution failed",
                logs=stdout + "\n" + stderr,
            )
```

### 5.3 AI 图片 Provider (API 调用)

```python
# src/execution/providers/ai_image.py

import asyncio
import logging
from pathlib import Path
from typing import Optional

import httpx

from .base import ExecutionProvider
from ..types import ProviderResult, ImageProvider

logger = logging.getLogger(__name__)


class AIImageProvider(ExecutionProvider):
    """AI 图片生成 Provider - 调用外部 API，不需要 Docker"""

    execution_type = "ai_image"
    docker_image = None  # 不使用 Docker

    # API 端点
    KLING_API = "https://api.klingai.com/v1/images/generations"
    DALLE_API = "https://api.openai.com/v1/images/generations"

    async def execute(
        self,
        content: str,  # prompt
        work_dir: str,
        options: dict,
        docker_client=None,
    ) -> ProviderResult:
        """直接调用 API 生成图片"""
        provider = ImageProvider(options.get("provider", "kling"))

        try:
            if provider == ImageProvider.KLING:
                image_data = await self._call_kling(content, options)
            elif provider == ImageProvider.DALLE:
                image_data = await self._call_dalle(content, options)
            else:
                return ProviderResult(
                    success=False,
                    error_message=f"Unsupported provider: {provider}",
                )

            # 保存图片
            output_path = Path(work_dir) / "output" / (options.get("filename") or "ai_image.png")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_data)

            return ProviderResult(
                success=True,
                output_files=[f"output/{output_path.name}"],
                metadata={"provider": provider.value},
            )

        except Exception as e:
            logger.error(f"AI image generation failed: {e}")
            return ProviderResult(
                success=False,
                error_message=str(e),
            )

    async def _call_kling(self, prompt: str, options: dict) -> bytes:
        """调用 Kling API"""
        api_key = options.get("api_key")  # 从配置注入
        aspect_ratio = options.get("aspect_ratio", "16:9")

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.KLING_API,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "style": "academic",
                },
            )
            response.raise_for_status()
            data = response.json()

            # 下载图片
            image_url = data["data"][0]["url"]
            img_response = await client.get(image_url)
            return img_response.content

    async def _call_dalle(self, prompt: str, options: dict) -> bytes:
        """调用 DALL-E API"""
        api_key = options.get("api_key")
        size = options.get("size", "1024x1024")

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.DALLE_API,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "size": size,
                    "n": 1,
                },
            )
            response.raise_for_status()
            data = response.json()

            image_url = data["data"][0]["url"]
            img_response = await client.get(image_url)
            return img_response.content

    def build_command(self, content: str, options: dict) -> list[str]:
        """不需要 Docker，此方法不会被调用"""
        return []

    async def process_result(self, *args, **kwargs) -> ProviderResult:
        """不需要，结果在 execute 中处理"""
        pass
```

## 6. Tools 实现

### 6.1 Tool 基类和注册

```python
# src/tools/execution/__init__.py

from .compile_latex import compile_latex_tool
from .plot_chart import plot_chart_tool
from .create_diagram import create_diagram_tool
from .generate_image import generate_image_tool

__all__ = [
    "compile_latex_tool",
    "plot_chart_tool",
    "create_diagram_tool",
    "generate_image_tool",
]


def get_execution_tools() -> list:
    """获取所有执行工具"""
    return [
        compile_latex_tool,
        plot_chart_tool,
        create_diagram_tool,
        generate_image_tool,
    ]
```

### 6.2 LaTeX 编译 Tool

```python
# src/tools/execution/compile_latex.py

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, Literal


class CompileLatexInput(BaseModel):
    """LaTeX 编译输入"""
    latex_source: str = Field(
        description="Complete LaTeX source code to compile"
    )
    compiler: Literal["pdflatex", "xelatex"] = Field(
        default="xelatex",
        description="Compiler to use. Use xelatex for Chinese content."
    )
    bibliography: Optional[str] = Field(
        default=None,
        description="Optional BibTeX bibliography content"
    )
    timeout: int = Field(
        default=120,
        description="Compilation timeout in seconds"
    )


@tool(args_schema=CompileLatexInput)
async def compile_latex_tool(
    latex_source: str,
    compiler: str = "xelatex",
    bibliography: Optional[str] = None,
    timeout: int = 120,
) -> str:
    """
    Compile LaTeX source code to PDF.

    Use this tool when you have generated complete LaTeX code and need to
    compile it into a PDF document. The tool supports both pdflatex and
    xelatex compilers.

    Args:
        latex_source: Complete LaTeX source code
        compiler: Compiler to use (pdflatex or xelatex)
        bibliography: Optional BibTeX content
        timeout: Compilation timeout in seconds

    Returns:
        Success message with output path, or error message.
    """
    # 实际执行由 middleware 注入 execution_service
    # 这里返回空字符串，真实实现在 middleware 中
    return ""


# Tool 实例
compile_latex = compile_latex_tool
```

### 6.3 Python 绘图 Tool

```python
# src/tools/execution/plot_chart.py

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, Literal


class PlotChartInput(BaseModel):
    """图表绘制输入"""
    code: str = Field(
        description="Python code using matplotlib/seaborn to generate the chart"
    )
    chart_type: Literal["line", "bar", "scatter", "heatmap", "histogram", "pie", "other"] = Field(
        default="other",
        description="Type of chart to generate"
    )
    output_format: Literal["png", "svg"] = Field(
        default="png",
        description="Output image format"
    )
    title: Optional[str] = Field(
        default=None,
        description="Chart title (for reference)"
    )


@tool(args_schema=PlotChartInput)
async def plot_chart_tool(
    code: str,
    chart_type: str = "other",
    output_format: str = "png",
    title: Optional[str] = None,
) -> str:
    """
    Generate data visualization charts using Python matplotlib/seaborn.

    Use this tool to create academic charts like line plots, bar charts,
    scatter plots, heatmaps, etc. The code must use matplotlib and save
    the figure using plt.savefig().

    Args:
        code: Python code to generate the chart
        chart_type: Type of chart being generated
        output_format: Output format (png or svg)
        title: Optional chart title for reference

    Returns:
        Success message with output path, or error message.
    """
    return ""


plot_chart = plot_chart_tool
```

## 7. Middleware 集成

### 7.1 ExecutionMiddleware

```python
# src/agents/middlewares/execution.py

import logging
from typing import Any

from langchain_core.messages import ToolMessage

from .base import BaseMiddleware
from src.execution.types import ExecutionRequest, ExecutionType
from src.execution.service import DockerExecutionService

logger = logging.getLogger(__name__)


class ExecutionMiddleware(BaseMiddleware):
    """执行工具中间件 - 处理执行类工具的调用"""

    # 需要处理的工具
    EXECUTION_TOOLS = {
        "compile_latex_tool": ExecutionType.LATEX_COMPILE,
        "plot_chart_tool": ExecutionType.PYTHON_PLOT,
        "create_diagram_tool": ExecutionType.MERMAID_DIAGRAM,
        "generate_image_tool": ExecutionType.AI_IMAGE,
    }

    def __init__(self, execution_service: DockerExecutionService):
        self.execution_service = execution_service

    async def before_tool(
        self,
        tool_name: str,
        tool_args: dict,
        config: dict,
    ) -> tuple[str, dict, dict] | None:
        """拦截执行工具调用"""

        if tool_name not in self.EXECUTION_TOOLS:
            return None  # 不处理，交给其他 middleware

        # 获取上下文信息
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        workspace_id = configurable.get("workspace_id")

        # 构建请求
        exec_type = self.EXECUTION_TOOLS[tool_name]
        request = self._build_request(
            exec_type=exec_type,
            tool_args=tool_args,
            thread_id=thread_id,
            workspace_id=workspace_id,
        )

        # 执行
        result = await self.execution_service.execute(request)

        # 返回 ToolMessage 替代真实调用
        # 这里返回 (tool_name, tool_args, extra) 会被后续处理
        # 我们需要在 after_tool 中返回结果

        # 将结果存储在 config 中供 after_tool 使用
        config["execution_result"] = result

        return None  # 继续正常流程，但在 after_tool 中替换结果

    async def after_tool(
        self,
        tool_name: str,
        tool_output: str,
        config: dict,
    ) -> str | None:
        """替换工具输出为实际执行结果"""

        if tool_name not in self.EXECUTION_TOOLS:
            return None

        result = config.pop("execution_result", None)
        if result:
            return result.to_tool_output()

        return None

    def _build_request(
        self,
        exec_type: ExecutionType,
        tool_args: dict,
        thread_id: str | None,
        workspace_id: str | None,
    ) -> ExecutionRequest:
        """根据工具参数构建执行请求"""

        if exec_type == ExecutionType.LATEX_COMPILE:
            return ExecutionRequest(
                execution_type=exec_type,
                content=tool_args["latex_source"],
                options={
                    "compiler": tool_args.get("compiler", "xelatex"),
                    "bibliography": tool_args.get("bibliography"),
                },
                timeout=tool_args.get("timeout", 120),
                thread_id=thread_id,
                workspace_id=workspace_id,
            )

        elif exec_type == ExecutionType.PYTHON_PLOT:
            return ExecutionRequest(
                execution_type=exec_type,
                content=tool_args["code"],
                options={
                    "format": tool_args.get("output_format", "png"),
                    "chart_type": tool_args.get("chart_type"),
                },
                thread_id=thread_id,
                workspace_id=workspace_id,
            )

        elif exec_type == ExecutionType.AI_IMAGE:
            return ExecutionRequest(
                execution_type=exec_type,
                content=tool_args["prompt"],
                options={
                    "provider": tool_args.get("provider", "kling"),
                    "aspect_ratio": tool_args.get("aspect_ratio", "16:9"),
                },
                thread_id=thread_id,
                workspace_id=workspace_id,
            )

        # ... 其他类型

        raise ValueError(f"Unknown execution type: {exec_type}")
```

## 8. Docker 镜像

### 8.1 TeXLive 镜像

```dockerfile
# docker/images/texlive/Dockerfile

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# 安装 TeXLive
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-science \
    texlive-bibtex-extra \
    texlive-xetex \
    texlive-lang-chinese \
    biber \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENTRYPOINT ["sh", "-c"]
```

### 8.2 Python 可视化镜像

```dockerfile
# docker/images/python-viz/Dockerfile

FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libfreetype6-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 包
RUN pip install --no-cache-dir \
    numpy \
    pandas \
    matplotlib \
    seaborn \
    scipy

WORKDIR /workspace

ENTRYPOINT ["python", "-c"]
```

### 8.3 Diagram 镜像

```dockerfile
# docker/images/diagram/Dockerfile

FROM node:18-slim

# 安装 Mermaid CLI 和 Graphviz
RUN apt-get update && apt-get install -y \
    graphviz \
    && npm install -g @mermaid-js/mermaid-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

ENTRYPOINT ["sh", "-c"]
```

## 9. 配置

### 9.1 执行服务配置

```yaml
# config/execution.yaml

execution:
  enabled: true

  docker:
    enabled: true
    base_url: null  # 使用默认
    timeout: 120

  providers:
    latex:
      enabled: true
      image: academiagpt/texlive:2024
      default_compiler: xelatex

    python_viz:
      enabled: true
      image: academiagpt/python-viz:1.0
      allowed_imports:
        - numpy
        - pandas
        - matplotlib
        - seaborn
        - scipy

    diagram:
      enabled: true
      image: academiagpt/diagram:1.0
      formats:
        - png
        - svg

    ai_image:
      enabled: true
      default_provider: kling
      providers:
        kling:
          api_key: ${KLING_API_KEY}
        dalle:
          api_key: ${OPENAI_API_KEY}
```

### 9.2 更新 docker-compose.yml

```yaml
# docker-compose.yml (更新)

version: '3.8'

services:
  postgres:
    # ... 现有配置

  redis:
    # ... 现有配置

  # 新增：执行服务（可选，用于预构建镜像）
  execution-builder:
    build:
      context: ./docker/images
      dockerfile: texlive/Dockerfile
    image: academiagpt/texlive:2024
    profiles:
      - build-images

volumes:
  postgres_data:
  redis_data:
```

## 10. 实现计划

### Phase 1: 核心框架 (3-4 天)

1. **类型和接口定义**
   - `src/execution/types.py`
   - `src/execution/base.py`

2. **Docker 客户端**
   - `src/execution/docker/client.py`
   - 基础容器管理

3. **安全检查器**
   - `src/execution/security/latex_sanitizer.py`
   - `src/execution/security/python_sanitizer.py`

### Phase 2: LaTeX 支持 (2-3 天)

1. **LaTeX Provider**
   - `src/execution/providers/latex.py`

2. **TeXLive 镜像**
   - `docker/images/texlive/Dockerfile`

3. **LaTeX Tool**
   - `src/tools/execution/compile_latex.py`

### Phase 3: Python 可视化 (2 天)

1. **Python Provider**
   - `src/execution/providers/python_viz.py`

2. **Python 镜像**
   - `docker/images/python-viz/Dockerfile`

3. **Plot Tool**
   - `src/tools/execution/plot_chart.py`

### Phase 4: 图表和 AI 生图 (2-3 天)

1. **Diagram Provider**
   - `src/execution/providers/diagram.py`

2. **AI Image Provider**
   - `src/execution/providers/ai_image.py`

3. **Tools**
   - `src/tools/execution/create_diagram.py`
   - `src/tools/execution/generate_image.py`

### Phase 5: 集成和测试 (2-3 天)

1. **ExecutionMiddleware**
   - `src/agents/middlewares/execution.py`

2. **服务注册**
   - 更新 middleware pipeline
   - 更新配置加载

3. **集成测试**
   - E2E 测试各功能
   - 性能测试

## 11. 后续扩展

### 11.1 容器池优化 (Phase 6)

- 预热容器池减少冷启动延迟
- 容器复用策略
- 资源监控和自动扩缩

### 11.2 高级 Skill (Phase 7)

- `LaTeXPaperSkill`: 完整论文生成流程
- `ImageOrchestratorSkill`: 智能图片生成编排

### 11.3 微服务迁移 (Future)

- 将 `DockerExecutionService` 替换为 `QueueExecutionService`
- 引入 Celery 任务队列
- 独立部署执行服务

---

*设计版本: 1.0*
*创建日期: 2026-03-10*
*作者: Claude Code*
