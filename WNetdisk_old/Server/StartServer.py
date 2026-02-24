
import sys
import ArgvDecoder as ad

HelpContent = """
Usage: StartServer.py [-options]

-options: 
    -ssl <certfile> <keyfile> <password>      :        创建一个SSL服务器
    -protocol <http1.1|http2|all>             :        指定使用的协议
    -python                                   :        是否启用Python文件
    -here                                     :        Create a config in this dir
"""



stru = ad.Structure(ssl=3)
argv = ad.decode(sys.argv, stru).__setitem__("name", "PyServerCommandObject")

handleCmd = False

if argv['-here']:
    from ConfigCreator import createConfig
    import os
    
    createConfig(os.getcwd()+"/pws_config.ini")
    print("Create config success.")

    handleCmd = True

print(HelpContent) if not handleCmd else None
print("-----------------------------")
print("Cannot decode command: ")
print(argv)