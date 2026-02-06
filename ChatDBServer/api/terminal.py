"""
终端交互模块
处理所有的终端输出、Markdown渲染、进度显示等
"""
import os
import sys
import time
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from model import Model
from conversation_manager import ConversationManager

# 初始化rich控制台
console = Console()


def clear_screen():
    """清屏"""
    os.system('cls' if os.name == 'nt' else 'clear')


def show_conversation_header(conversation):
    """显示对话标题头"""
    title = conversation.get('title', '新对话')
    conv_id = conversation.get('conversation_id', '?')
    msg_count = len(conversation.get('messages', []))
    
    console.print()
    console.print(Panel(
        f"[bold cyan]{title}[/bold cyan]\n"
        f"[dim]对话ID: {conv_id} | 消息数: {msg_count}[/dim]",
        border_style="cyan",
        padding=(0, 2)
    ))
    console.print()


def print_function_call(name, arguments, elapsed=None):
    """打印函数调用信息"""
    if elapsed:
        console.print(f"[green]✓[/green] {name} [dim]({elapsed:.2f}秒)[/dim]")
    else:
        console.print(f"[cyan]调用函数: {name}[/cyan]")


def print_function_result(result):
    """打印函数返回结果"""
    try:
        import json
        result_display = json.dumps(result, indent=2, ensure_ascii=False)
        
        # 限制显示长度
        max_display_length = 500
        if len(result_display) > max_display_length:
            result_display = result_display[:max_display_length] + "\n... (结果过长，已截断)"
        
        # 使用Panel包裹
        syntax = Syntax(result_display, "json", theme="monokai", background_color="default")
        console.print(Panel(
            syntax, 
            title=f"[dim]返回结果[/dim]", 
            border_style="dim cyan",
            padding=(0, 1)
        ))
    except:
        console.print(Panel(
            str(result)[:500],
            title="[dim]返回结果[/dim]",
            border_style="dim cyan",
            padding=(0, 1)
        ))


def print_markdown(content, show_panel=True):
    """打印Markdown内容"""
    md = Markdown(content)
    if show_panel:
        console.print(Panel(md, title="🤖 AI助手", border_style="cyan"))
    else:
        console.print(md)


def chat_with_markdown(model, msg, stream=True, show_panel=True):
    """
    使用Markdown渲染进行对话
    
    Args:
        model: Model实例
        msg: 用户消息
        stream: 是否流式输出
        show_panel: 是否显示面板
        
    Returns:
        完整的回复内容
    """
    accumulated_content = ""
    function_calls = {}  # 记录函数调用的开始时间
    
    try:
        is_tty = sys.stdout.isatty()
        
        if stream and is_tty:
            # 流式输出 + Live渲染
            with Live(console=console, refresh_per_second=10) as live:
                for chunk in model.sendMessage(msg, stream=True):
                    if chunk["type"] == "reasoning":
                        # 思考过程 - 用暗淡颜色显示
                        console.print(f"[dim cyan]💭 思考: {chunk['content'][:100]}...[/dim cyan]")
                    
                    elif chunk["type"] == "content":
                        accumulated_content += chunk["content"]
                        # 实时更新Markdown渲染
                        md = Markdown(accumulated_content)
                        if show_panel:
                            live.update(Panel(md, title="🤖 AI助手", border_style="cyan"))
                        else:
                            live.update(md)
                    
                    elif chunk["type"] == "function_call":
                        # 记录函数调用开始时间
                        func_name = chunk["name"]
                        function_calls[func_name] = time.time()
                        console.print(f"\n[cyan]⚙ 调用函数: {func_name}[/cyan]")
                    
                    elif chunk["type"] == "function_result":
                        # 计算耗时并显示结果
                        func_name = chunk["name"]
                        if func_name in function_calls:
                            elapsed = time.time() - function_calls[func_name]
                            console.print(f"[green]✓[/green] {func_name} [dim]({elapsed:.2f}秒)[/dim]")
                        print_function_result(chunk["result"])
                    
                    elif chunk["type"] == "web_search":
                        console.print(f"[yellow]🔍 {chunk['content']}[/yellow]")
                    
                    elif chunk["type"] == "error":
                        console.print(f"\n[red]错误: {chunk['content']}[/red]")
                    
                    elif chunk["type"] == "done":
                        break
        else:
            # 非流式或非TTY环境
            for chunk in model.sendMessage(msg, stream=False):
                if chunk["type"] == "reasoning":
                    console.print(f"[dim cyan]💭 思考: {chunk['content'][:100]}...[/dim cyan]")
                
                elif chunk["type"] == "content":
                    accumulated_content += chunk["content"]
                
                elif chunk["type"] == "function_call":
                    func_name = chunk["name"]
                    function_calls[func_name] = time.time()
                    console.print(f"[cyan]⚙ 调用函数: {func_name}[/cyan]")
                
                elif chunk["type"] == "function_result":
                    func_name = chunk["name"]
                    if func_name in function_calls:
                        elapsed = time.time() - function_calls[func_name]
                        console.print(f"[green]✓[/green] {func_name} [dim]({elapsed:.2f}秒)[/dim]")
                    print_function_result(chunk["result"])
                
                elif chunk["type"] == "web_search":
                    console.print(f"[yellow]🔍 {chunk['content']}[/yellow]")
                
                elif chunk["type"] == "title":
                    # 生成了标题，更新显示
                    console.print(f"[dim]🏷 对话标题: {chunk['title']}[/dim]")
                
                elif chunk["type"] == "error":
                    console.print(f"[red]错误: {chunk['content']}[/red]")
                
                elif chunk["type"] == "done":
                    break
            
            # 一次性渲染完整内容
            if accumulated_content:
                print_markdown(accumulated_content, show_panel)
    
    except Exception as e:
        console.print(f"[red]异常: {str(e)}[/red]")
        import traceback
        traceback.print_exc()
    
    return accumulated_content


def interactive_chat(username="test_user"):
    """交互式对话"""
    # 切换到正确的工作目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    os.chdir(parent_dir)
    
    clear_screen()
    console.print()
    console.print("[bold cyan]✨ ChatDB AI助手[/bold cyan]")
    console.print("[dim]输入 'exit' 或 'quit' 退出[/dim]")
    console.print("[dim]命令: /list 列出对话 | /change <id> 切换对话 | /new 新建对话[/dim]")
    console.print()
    
    conversation_manager = ConversationManager(username)
    model = Model(username, auto_create=False)  # 不立即创建对话，等第一次消息时创建
    
    # 显示当前状态
    if model.conversation_id:
        conversation = conversation_manager.get_conversation(model.conversation_id)
        show_conversation_header(conversation)
    else:
        console.print("[dim]💬 准备开始对话...[/dim]\n")
    

    
    while True:
        try:
            user_input = input(">>> ")
            
            if user_input.lower() in ['exit', 'quit', 'q']:
                console.print("[yellow]再见！[/yellow]")
                break
            
            if not user_input.strip():
                continue
            
            # 处理命令
            if user_input.startswith('/'):
                command_parts = user_input.split(maxsplit=1)
                command = command_parts[0].lower()
                
                if command == '/list':
                    # 列出所有对话
                    conversations = conversation_manager.list_conversations()
                    
                    if not conversations:
                        console.print("[dim]没有任何对话记录[/dim]\n")
                        continue
                    
                    console.print(f"\n[bold]📋 对话列表[/bold] [dim](共 {len(conversations)} 个)[/dim]\n")
                    for conv in conversations:
                        current_mark = "[bold green]▶[/bold green]" if model.conversation_id == conv['conversation_id'] else " "
                        title_display = conv.get('title', '未命名对话')[:30]
                        console.print(
                            f"{current_mark} [cyan]{conv['conversation_id'].rjust(3)}[/cyan] | "
                            f"[bold]{title_display}[/bold] "
                            f"[dim]({conv['message_count']}条消息)[/dim]"
                        )
                    console.print()
                    
                elif command == '/change':
                    # 切换对话
                    if len(command_parts) < 2:
                        console.print("[red]用法: /change <对话ID>[/red]\n")
                        continue
                    
                    new_conv_id = command_parts[1].strip()
                    
                    try:
                        # 验证对话是否存在
                        conv_data = conversation_manager.get_conversation(new_conv_id)
                        
                        # 切换对话
                        model = Model(username, conversation_id=new_conv_id)
                        
                        # 清屏并显示对话
                        clear_screen()
                        show_conversation_header(conv_data)
                        
                        # 显示所有历史消息（完整内容）
                        messages = conv_data.get('messages', [])
                        if messages:
                            console.print("[bold]📜 历史消息:[/bold]\n")
                            for msg in messages:
                                role = msg['role']
                                content = msg['content']
                                
                                if role == 'user':
                                    console.print(f"[bold cyan]👤 USER:[/bold cyan]")
                                    console.print(content)
                                elif role == 'assistant':
                                    console.print(f"\n[bold green]🤖 ASSISTANT:[/bold green]")
                                    print_markdown(content, show_panel=False)
                                
                                console.print()
                            
                            console.print("[dim]─[/dim]" * 60)
                            console.print(f"[dim]💡 已加载 {len(messages)} 条消息，模型将基于以上上下文继续对话[/dim]\n")
                        else:
                            console.print("[dim]🆕 这是一个新对话[/dim]\n")
                        
                    except ValueError as e:
                        console.print(f"[red]错误: {str(e)}[/red]\n")
                        
                elif command == '/new':
                    # 创建新对话
                    model = Model(username)
                    clear_screen()
                    console.print("\n[green]✓[/green] [bold]已开始新对话[/bold]\n")
                    
                else:
                    console.print(f"[red]未知命令: {command}[/red]")
                    console.print("[dim]可用命令: /list, /change <id>, /new[/dim]\n")
                
                continue
            
            # 普通消息
            print()  # 空行
            chat_with_markdown(model, user_input, stream=True, show_panel=True)
            print()  # 空行
            
        except KeyboardInterrupt:
            console.print("\n[yellow]已中断[/yellow]")
            break
        except EOFError:
            break
        except Exception as e:
            console.print(f"[red]错误: {str(e)}[/red]")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    interactive_chat()
