# cspell:disable

# pro testy na lokále

# print verze pythonu
from libs.JBLibs.c_menu import printBlock
from libs.JBLibs.helper import cls
from datetime import datetime as dt

# x=systemd.c_service('node-red-node_team_4')

# x=systemd.c_service.list('postgresql-8.3.servicex')

# c=x.status()

# timestamp = "Fri 2024-10-25 09:10:42 CEST"
# active_time = parser.parse(timestamp)

# uptime = int(dt.now().timestamp() - active_time.timestamp())
# s=strTime(str(uptime)+"s")

cls()

def prn(obalChar="",bracket="",minwidth=0):

    tst=[    
        [
            "Zadejte uživatelské jméno:",
            "q = Konec"
        ],    
        # [
        #     ["Zadejte uživatelské jméno:"],
        #     ["q = Konec"]
        # ],
        # [
        #     ["Zadejte uživatelské jméno:\nNext Line inline"],
        #     "q = Konec",
        # ],
        # [
        #     ["Zadejte uživatelské jméno","Next Line split"],
        #     "q = Konec"
        # ],
        # [    
        #     [
        #         ["Zadejte uživatelské jméno","right side"],
        #         "Next Line"
        #     ],
        #     "q = Konec"
        # ],
        # [
        #     [
        #         "Test\nNext Line after LF",
        #         ["","right side"],
        #         "Next Line",
        #         "-"
        #     ],
        #     [
        #         ["n","q = Konec"]
        #     ]
        # ]
    ]
    for x,y in tst:
        printBlock(x,y,eof=True,charObal=obalChar,rightTxBrackets=bracket,min_width=minwidth)
        
# print( "start at {0}".format(dt.now().strftime("%Y-%m-%d %H:%M:%S")) )

# print("x"*100 +"\nprn()\n")
# prn()

# print("x"*100 +"\nprn(obalChar='*')\n")
# prn("*","<")

# print("x"*100 +"\nprn(obalChar='*',bracket='[', minwidth=50)\n") 
# prn("*","[",50)

# print("x"*100 +"\nprn(obalChar='*',bracket='[', minwidth=50)\n") 
# prn("|*","[",50)

# print("x"*100 +"\nprn(obalChar='',bracket='[',minwidth=50)\n")
# prn("","[",50)

# from libs.JBLibs.systemdService import bytesTx

# print(bytesTx(1024))
# print(bytesTx(1024*1024))
# print(bytesTx('1kB'))
# print(bytesTx('1,15kB'))
# print(bytesTx('1kB').bytes)
# print(bytesTx('2.15MB'))
# print(bytesTx('2.15MB').bytes)
# print(bytesTx('25B'))
# print(bytesTx('2048MB'))
# print('test exa')
# x=bytesTx('154E')
# print(x)
# x=bytesTx(x.bytes)
# print(x)
# print(x.bytes)
# print(bytesTx(177549911709454434304000000))

from libs.JBLibs.input import select, select_item

x=select("Testovací select",[
    select_item("První",data="první výběr"),
    select_item("Druhý","dru",data="druhý výběr"),
],80)
print(x.item.data if x.item else "ESC, nebylo nic vybráno")