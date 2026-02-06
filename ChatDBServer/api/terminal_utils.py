"""
终端输出工具模块
提供Markdown渲染和格式化输出功能
"""
import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

# 初始化控制台
console = Console()


def print_markdown(text, title=None, border_style="cyan"):
    """
    在终端打印Markdown格式的文本
    
    Args:
        text: Markdown文本内容
        title: 可选的面板标题
        border_style: 边框样式颜色
    """
    md = Markdown(text)
    if title:
        console.print(Panel(md, title=title, border_style=border_style))
    else:
        console.print(md)


def print_code(code, language="python", theme="monokai", line_numbers=True):
    """
    在终端打印带语法高亮的代码
    
    Args:
        code: 代码文本
        language: 编程语言
        theme: 高亮主题
        line_numbers: 是否显示行号
    """
    syntax = Syntax(code, language, theme=theme, line_numbers=line_numbers)
    console.print(syntax)


def print_success(message):
    """打印成功消息（绿色）"""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message):
    """打印错误消息（红色）"""
    console.print(f"[bold red]✗[/bold red] {message}")


def print_info(message):
    """打印信息消息（蓝色）"""
    console.print(f"[bold blue]ℹ[/bold blue] {message}")


def print_warning(message):
    """打印警告消息（黄色）"""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def is_tty():
    """检查是否是TTY环境"""
    return sys.stdout.isatty()


# 测试代码
if __name__ == "__main__":
    print("\n=== 测试输出工具 ===\n")
    
    # 测试Markdown
    print_markdown("""
# 测试标题

这是一段**加粗**文本和*斜体*文本。

- 列表项1
- 列表项2
""", title="Markdown示例")
    
    print()
    
    # 测试状态消息
    print_success("操作成功完成")
    print_error("发生了错误")
    print_info("这是一条信息")
    print_warning("这是一条警告")
    
    print()
    
    # 测试代码高亮
    print_code("""
def hello():
    print("Hello, World!")
""")
    
    print(f"\nTTY环境: {is_tty()}")
