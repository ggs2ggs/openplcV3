# -----------------------------------------------------------------------------
# Copyright 2015 Thiago Alves
# This file is part of the OpenPLC Software Stack.

# OpenPLC is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# OpenPLC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with OpenPLC.  If not, see <http://www.gnu.org/licenses/>.
# ----------------------------------------------------------------------------

import sqlite3
from sqlite3 import Error
import os
import subprocess
import platform
import serial.tools.list_ports
import random
import datetime
import time
import sys

import flask
from flask import redirect, request, render_template, url_for

import flask_login
from flask_login import current_user, login_required

from . import HERE_PATH, ROOT_PATH, ETC_PATH
from . import pages
from . import openplc
from . import monitoring as monitor


# -----------------------------------------------------
# Database stuff
# -----------------------------------------------------
DB_FILE = "openplc.db"

def db_connection():
    try:
        conn = sqlite3.connect(DB_FILE)
        return conn
    except Error as e:
        print(e)
    return None

def db_query(sql, args=(), single=False, as_list=False):
    """ Opens db, execute query, close then return results.
    Querying is one function atmo, as issues with multithread app.

    :param sql: str with sql and :params placeholders
    :param args: dict with arg values
    :param single: return only one row
    :param as_list: True returns a row in a list, otherwise a dict
    :return: rows/row, err
    """
    conn = db_connection()
    if not conn:
        return None, "Cannot connect db"
    try:
        cur = conn.cursor()
        cur.execute(sql, args)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        ## This is a workaround until schema changes maybe, converts to dict
        col_names = [c[0].lower() for c in cur.description]
        row_dict = []
        for ridx, row in enumerate(rows):
            d = {}
            for cidx, cn in enumerate(col_names):
                d[cn] = row[cidx]
            row_dict.append(d)

        if not single:
            return rows if as_list else row_dict, None

        if len(rows) == 0:
            return None, "No Rows"

        if len(rows) > 1:
            return None, "More than one row"

        return rows[0] if as_list else row_dict[0], None

    except Error as e:
        print("error connecting to the database" + str(e))
        return None, str(e)


def db_insert(table, flds):
    sql = "insert into %s (" % table
    keys = sorted(flds.keys())
    sql += ",".join(keys)
    sql += ") values ("
    sql += ",".join(["?" for i in range(0, len(keys))])
    sql += ");"

    conn = db_connection()
    if not conn:
        return None, "Cannot connect db"

    try:
        cur = conn.cursor()
        cur.execute(sql, [flds[k] for k in keys])
        conn.commit()

        ## get inserted id
        sql = "select last_insert_rowid()"
        cur.execute(sql)
        row = cur.fetchone()
        return row[0], None

    except Error as e:
        return None, str(e)


def db_update(table, flds, p_name, p_id):
    sql = "update %s set " % table
    keys = sorted(flds.keys())
    sql += ",".join(["%s=?" % k for k in keys])
    sql += " where %s = ?;" % p_name
    vals = [flds[k] for k in keys]
    vals.append(p_id)

    conn = db_connection()
    if not conn:
        return "Cannot connect db"
    try:
        cur = conn.cursor()
        cur.execute(sql, vals)
        conn.commit()
        return None

    except Error as e:
        print("error connecting to the database" + str(e))
        return str(e)



#------------------------------------------------
# Flask app
app = flask.Flask(__name__)
app.secret_key = "openplciscool1234564561" #str(os.urandom(16))

app.config['SECRET_KEY'] = app.secret_key
app.config['TEMPLATES_AUTO_RELOAD'] = True


#------------------------------------------------
#  Login + Security
login_manager = flask_login.LoginManager()
login_manager.login_view = "/login" # FIXME
login_manager.init_app(app)

class User:
    def __init__(self):

        self.is_active = True
        self.is_authenticated = True

        self.user_id = None
        self.username = None
        self.name = None
        self.pict_file = None

    def get_id(self):
        return self.user_id

@login_manager.user_loader
def user_loader(user_id):
    """Get user details for flask admin"""
    sql = "SELECT user_id, username, name, pict_file FROM Users "
    sql += ' where user_id=? '
    row, err = db_query(sql, [user_id], single=True)
    if err:
        print(err)
        return None

    user = User()
    user.user_id = "%s" % row["user_id"]
    user.username = row["username"]
    user.name = row["name"]
    user.pict_file = str(row["pict_file"])
    return user


@login_manager.unauthorized_handler
def unauthorized_handler():
    return 'Unauthorized'


#------------------------------------------------------------------
#  OpenPLC Runtime
#------------------------------------------------------------------
openplc_runtime = openplc.runtime()

DEVICE_PROTOCOLS = [
    {'protocol': 'Uno', 'label': 'Arduino Uno'},
    {'protocol': 'Mega', 'label': 'Arduino Mega'},
    {'protocol': 'ESP32', 'label': 'ESP32'},
    {'protocol': 'ESP8266', 'label': 'ESP8266'},
    {'protocol': 'TCP', 'label': 'Generic Modbus TCP Device'},
    {'protocol': 'RTU', 'label': 'Generic Modbus RTU Device'}
]

def configure_runtime():
    global openplc_runtime

    rows, err = db_query("SELECT * FROM Settings")
    if err:
        print(err)
        # TODO error handling
        return

    for row in rows:
        if row[0] == "Modbus_port":
            if row[1] != "disabled":
                print("Enabling Modbus on port " + str(int(row[1])))
                openplc_runtime.start_modbus(int(row[1]))
            else:
                print("Disabling Modbus")
                openplc_runtime.stop_modbus()

        elif row[0] == "Dnp3_port":
            if row[1] != "disabled":
                print("Enabling DNP3 on port " + str(int(row[1])))
                openplc_runtime.start_dnp3(int(row[1]))
            else:
                print("Disabling DNP3")
                openplc_runtime.stop_dnp3()

        elif row[0] == "Enip_port":
            if row[1] != "disabled":
                print("Enabling EtherNet/IP on port " + str(int(row[1])))
                openplc_runtime.start_enip(int(row[1]))
            else:
                print("Disabling EtherNet/IP")
                openplc_runtime.stop_enip()

        elif row[0] == "Pstorage_polling":
            if row[1] != "disabled":
                print("Enabling Persistent Storage with polling rate of " + str(int(row[1])) + " seconds")
                openplc_runtime.start_pstorage(int(row[1]))
            else:
                print("Disabling Persistent Storage")
                openplc_runtime.stop_pstorage()
                delete_persistent_file()


def delete_persistent_file():
    if os.path.isfile("persistent.file"):
        os.remove("persistent.file")
    print("persistent.file removed!")


def generate_mbconfig():
    database = "../etc/openplc.db"
    conn = create_connection(database)
    if (conn != None):
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM Slave_dev")
            row = cur.fetchone()
            num_devices = int(row[0])
            mbconfig = 'Num_Devices = "' + str(num_devices) + '"'
            cur.close()
            
            cur=conn.cursor()
            cur.execute("SELECT * FROM Settings")
            rows = cur.fetchall()
            cur.close()
                    
            for row in rows:
                if (row[0] == "Slave_polling"):
                    slave_polling = str(row[1])
                elif (row[0] == "Slave_timeout"):
                    slave_timeout = str(row[1])
                    
            mbconfig += '\nPolling_Period = "' + slave_polling + '"'
            mbconfig += '\nTimeout = "' + slave_timeout + '"'
            
            cur = conn.cursor()
            cur.execute("SELECT * FROM Slave_dev")
            rows = cur.fetchall()
            cur.close()
            conn.close()
            
            device_counter = 0
            for row in rows:
                mbconfig += """
# ------------
#   DEVICE """
                mbconfig += str(device_counter)
                mbconfig += """
# ------------
"""
                mbconfig += 'device' + str(device_counter) + '.name = "' + str(row[1]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.slave_id = "' + str(row[3]) + '"\n'
                if (str(row[2]) == 'ESP32' or str(row[2]) == 'ESP8266' or str(row[2]) == 'TCP'):
                    mbconfig += 'device' + str(device_counter) + '.protocol = "TCP"\n'
                    mbconfig += 'device' + str(device_counter) + '.address = "' + str(row[9]) + '"\n'
                else:
                    mbconfig += 'device' + str(device_counter) + '.protocol = "RTU"\n'
                    if (str(row[4]).startswith("COM")):
                        port_name = "/dev/ttyS" + str(int(str(row[4]).split("COM")[1]) - 1)
                    else:
                        port_name = str(row[4])
                    mbconfig += 'device' + str(device_counter) + '.address = "' + port_name + '"\n'
                mbconfig += 'device' + str(device_counter) + '.IP_Port = "' + str(row[10]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.RTU_Baud_Rate = "' + str(row[5]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.RTU_Parity = "' + str(row[6]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.RTU_Data_Bits = "' + str(row[7]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.RTU_Stop_Bits = "' + str(row[8]) + '"\n\n'
                
                mbconfig += 'device' + str(device_counter) + '.Discrete_Inputs_Start = "' + str(row[11]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Discrete_Inputs_Size = "' + str(row[12]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Coils_Start = "' + str(row[13]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Coils_Size = "' + str(row[14]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Input_Registers_Start = "' + str(row[15]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Input_Registers_Size = "' + str(row[16]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Holding_Registers_Read_Start = "' + str(row[17]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Holding_Registers_Read_Size = "' + str(row[18]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Holding_Registers_Start = "' + str(row[19]) + '"\n'
                mbconfig += 'device' + str(device_counter) + '.Holding_Registers_Size = "' + str(row[20]) + '"\n'
                device_counter += 1
                
            with open('./mbconfig.cfg', 'w+') as f: f.write(mbconfig)
            
        except Error as e:
            print("error connecting to the database" + str(e))
    else:
        print("Error opening DB")
                

#-----------------------------------------------------------------
#=  Template Stuff
#-----------------------------------------------------------------

# site navigation; Note selected is passed a {{c.page}}
# see https://fontawesome.bootstrapcheatsheets.com/ for icons
Nav = [
    {"label": "Dashboard", "page": "dashboard", "icon": "fa-home"},
    {"label": "Programs", "page": "programs", "icon": "fa-braille"},
    {"label": "Slave Devices", "page": "slaves", "icon": "fa-sitemap"},
    {"label": "Monitoring", "page": "monitoring", "icon": "fa-signal"},
    {"label": "Hardware", "page": "hardware", "icon": "fa-microchip"},
    {"label": "Users", "page": "users", "icon": "fa-users"},
    {"label": "Settings", "page": "settings", "icon": "fa-cog"},
    {"label": "Logout", "page": "logout", "icon": "fa-sign-out"},
]
def nav_icon(page, default="fa-stop"):
    if page:
        for n in Nav:
            if n['page'] == page:
                return n['icon']
    return default

@app.context_processor
def inject_template_vars():
    # Put the runtime and navigation into template context
    return dict(nav=Nav, runtime=openplc_runtime)

class TemplateContext(object):
    pass

def make_context(page, **kwargs):
    c = TemplateContext()
    c.error = None
    c.page = page
    c.icon = nav_icon(page)
    return c


def draw_top_div():
    global openplc_runtime
    top_div = ("<div class='top'>"
    "<img src='/static/openplc_logo.gif' alt='OpenPLC' style='width:111px;height:45px;padding:5px 0px 0px 10px;float:left'>")
    
    if (openplc_runtime.status() == "Running"):
        top_div += "<h3 style='font-family:\"Roboto\", sans-serif; font-size:18px; color:white; padding:13px 111px 0px 0px; margin: 0px 0px 0px 0px'><center><span style='color: #02EE07'>Running: </span>" + openplc_runtime.project_name + "</center></h3>"
    elif (openplc_runtime.status() == "Compiling"):
        top_div += "<h3 style='font-family:\"Roboto\", sans-serif; font-size:18px; color:white; padding:13px 111px 0px 0px; margin: 0px 0px 0px 0px'><center><span style='color: Yellow'>Compiling: </span>" + openplc_runtime.project_name + "</center></h3>"
    else:
        top_div += "<h3 style='font-family:\"Roboto\", sans-serif; font-size:18px; color:white; padding:13px 111px 0px 0px; margin: 0px 0px 0px 0px'><center><span style='color: Red'>Stopped: </span>" + openplc_runtime.project_name + "</center></h3>"
    
    top_div += "<div class='user'><img src='"
    if (flask_login.current_user.pict_file == "None"):
        top_div += "/static/default-user.png"
    else:
        top_div += flask_login.current_user.pict_file
    
    top_div += "' alt='User' style='width:50px;height:45px;padding:5px 5px 0px 5px;float:right'>"
    top_div += "<h3 style='font-family:\"Roboto\", sans-serif; font-size:18px; color:white; padding:13px 0px 0px 0px; margin: 0px 0px 0px 0px'>" + flask_login.current_user.name + "</h3>"
    top_div += "</div></div>"
    
    return top_div    


def draw_status():
    global openplc_runtime
    status_str = ""
    if (openplc_runtime.status() == "Running"):
        status_str = "<center><h3 style='font-family:\"Roboto\", sans-serif; font-size:18px; color:white; padding:0px 0px 0px 0px;'>Status: <i>Running</i></span></center></h3>"
        status_str += "<a href='stop_plc' class='button' style='width: 210px; height: 53px; margin: 0px 20px 0px 20px;'><b>Stop PLC</b></a>"
    else:
        status_str = "<center><h3 style='font-family:\"Roboto\", sans-serif; font-size:18px; color:white; padding:0px 0px 0px 0px;'>Status: <i>Stopped</i></span></center></h3>"
        status_str += "<a href='start_plc' class='button' style='width: 210px; height: 53px; margin: 0px 20px 0px 20px;'><b>Start PLC</b></a>"
    
    return status_str    


def draw_blank_page():
    return_str = pages.w3_style + pages.dashboard_head + draw_top_div() + """
            <div class='main'>
                <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                    <br>
                    <br>
                    <div class="w3-bar-item"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></div>
                    <div class="w3-bar-item"><img src='/static/programs-icon-64x64.png' alt='Programs' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></div>
                    <div class="w3-bar-item"><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></div>
                    <div class="w3-bar-item"><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></div>
                    <div class="w3-bar-item"><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></div>
                    <div class="w3-bar-item"><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></div>
                    <div class="w3-bar-item"><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></div>
                    <div class="w3-bar-item"><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></div>
                    <br>
                    <br>
                </div>
                <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>"""
    return return_str
    
def draw_compiling_page():
    return_str = draw_blank_page()
    return_str += """
                    <h2>Compiling program</h2>
                    <textarea id='mytextarea' style='height:500px; resize:vertical'>
loading logs...
                    </textarea>
                    <br><br><center><a href='dashboard' id='dashboard_button' class='button' style='background-color: #EDEDED; pointer-events: none; width: 310px; height: 53px; margin: 0px 20px 0px 20px;'><b>Go to Dashboard</b></a></center>
                </div>
            </div>
        </div>
    </body>
    
    <script>
        (function (global)
        {
            if(typeof (global) === "undefined")
            {
                throw new Error("window is undefined");
            }
            
            var _hash = "!";
            var noBackPlease = function () 
            {
                global.location.href += "#";

                // making sure we have the fruit available for juice....
                // 50 milliseconds for just once do not cost much (^__^)
                global.setTimeout(function () 
                {
                    global.location.href += "!";
                }, 50);
            };
            
            // Earlier we had setInerval here....
            global.onhashchange = function () 
            {
                if (global.location.hash !== _hash) 
                {
                    global.location.hash = _hash;
                }
            };

            global.onload = function () 
            {
                loadData();
                noBackPlease();
                
                // disables backspace on page except on input fields and textarea..
                document.body.onkeydown = function (e) 
                {
                    var elm = e.target.nodeName.toLowerCase();
                    if (e.which === 8 && (elm !== 'input' && elm  !== 'textarea')) 
                    {
                        e.preventDefault();
                    }
                    // stopping event bubbling up the DOM tree..
                    e.stopPropagation();
                };
            };
        })(window);
        
        var req;
        
        function loadData()
        {
            url = 'compilation-logs'
            try
            {
                req = new XMLHttpRequest();
            } catch (e) 
            {
                try
                {
                    req = new ActiveXObject('Msxml2.XMLHTTP');
                } catch (e) 
                {
                    try 
                    {
                        req = new ActiveXObject('Microsoft.XMLHTTP');
                    } catch (oc) 
                    {
                        alert('No AJAX Support');
                        return;
                    }
                }
            }
            
            req.onreadystatechange = processReqChange;
            req.open('GET', url, true);
            req.send(null);
        }
        
        function processReqChange()
        {
            //If req shows 'complete'
            if (req.readyState == 4)
            {
                compilation_logs = document.getElementById('mytextarea');
                dashboard_button = document.getElementById('dashboard_button');
                
                //If 'OK'
                if (req.status == 200)
                {
                    //Update textarea text
                    compilation_logs.value = req.responseText;
                    if ((req.responseText.search("Compilation finished with errors!") != -1) || (req.responseText.search("Compilation finished successfully!") != -1))
                    {
                        dashboard_button.style.background='#E02222'
                        dashboard_button.style.pointerEvents='auto'
                    }
                    
                    //Start a new update timer
                    timeoutID = setTimeout('loadData()', 1000);
                }
                else
                {
                    compilation_logs.value = 'There was a problem retrieving the logs. Error: ' + req.statusText;
                }
            }
        }
    </script>
</html>"""
    return return_str

#
# @login_manager.user_loader
# def user_loader(username):
#     database = "../etc/openplc.db"
#     conn = create_connection(database)
#     if (conn != None):
#         try:
#             cur = conn.cursor()
#             cur.execute("SELECT username, password, name, pict_file FROM Users")
#             rows = cur.fetchall()
#             cur.close()
#             conn.close()
#
#             for row in rows:
#                 if (row[0] == username):
#                     user = User()
#                     user.id = row[0]
#                     user.name = row[2]
#                     user.pict_file = str(row[3])
#                     return user
#             return
#
#         except Error as e:
#             print("error connecting to the database" + str(e))
#             return
#     else:
#         return


# @login_manager.request_loader
# def request_loader(request):
#     username = request.form.get('username')
#
#     database = "../etc/openplc.db"
#     conn = create_connection(database)
#     if (conn != None):
#         try:
#             cur = conn.cursor()
#             cur.execute("SELECT username, password, name, pict_file FROM Users")
#             rows = cur.fetchall()
#             cur.close()
#             conn.close()
#
#             for row in rows:
#                 if (row[0] == username):
#                     user = User()
#                     user.id = row[0]
#                     user.name = row[2]
#                     user.pict_file = str(row[3])
#                     user.is_authenticated = (request.form['password'] == row[1])
#                     return user
#             return
#
#         except Error as e:
#             print("error connecting to the database" + str(e))
#             return
#     else:
#         return

#
# @app.before_request
# def before_request():
#     flask.session.permanent = True
#     app.permanent_session_lifetime = datetime.timedelta(minutes=5)
#     flask.session.modified = True
        
@app.route('/')
def index():
    if flask_login.current_user.is_authenticated:
        return flask.redirect(flask.url_for('dashboard'))
    else:
        return flask.redirect(flask.url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def p_login():
    # This is login page.. so if auth, goto dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    ctx = make_context("login")

    if request.method == "POST":
        username = request.form['oplc_username']
        password = request.form['oplc_secret']

        if username and password:

            sql = "SELECT user_id, username, password, name, pict_file FROM Users"
            sql += " where username=? and password=? "
            row, err = db_query(sql, (username, password), single=True)
            if err:
                ctx.error = err

            if not row:
                ctx.error = "Incorrect User or Password "

            else:
                # Login User
                user = User()
                user.user_id = unicode(row['user_id'])
                user.username = row['username']
                user.name = row['name']
                user.pict_file = row['pict_file']
                print(user)
                flask_login.login_user(user, remember=True, fresh=True, )
                return flask.redirect(flask.url_for('dashboard'))

    return render_template("login.html", c=ctx)


@app.route('/start_plc')
def start_plc():
    global openplc_runtime
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        monitor.stop_monitor()
        openplc_runtime.start_runtime()
        time.sleep(1)
        configure_runtime()
        monitor.cleanup()
        monitor.parse_st(openplc_runtime.project_file)
        return flask.redirect(flask.url_for('dashboard'))


@app.route('/stop_plc')
def stop_plc():
    global openplc_runtime
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        openplc_runtime.stop_runtime()
        time.sleep(1)
        monitor.stop_monitor()
        return flask.redirect(flask.url_for('dashboard'))


@app.route('/runtime_logs')
def runtime_logs():
    global openplc_runtime
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        return openplc_runtime.logs()


@app.route('/dashboard')
def dashboard():
    global openplc_runtime
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        monitor.stop_monitor()
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        return_str = pages.w3_style + pages.dashboard_head + draw_top_div()
        return_str += """
            <div class='main'>
                <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                    <br>
                    <br>
                    <a href='dashboard' class='w3-bar-item w3-button' style='background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px'><img src='/static/home-icon-64x64.png' alt='Dashboard' style='width:47px;height:39px;padding:7px 15px 0px 0px;float:left'><img src='/static/arrow.png' style='width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Dashboard</p></a>
                    <a href='programs' class='w3-bar-item w3-button'><img src='/static/programs-icon-64x64.png' alt='Programs' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></a>
                    <a href='modbus' class='w3-bar-item w3-button'><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></a>
                    <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                    <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                    <a href='users' class='w3-bar-item w3-button'><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></a>
                    <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                    <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                    <br>
                    <br>"""
        return_str += draw_status()
        return_str += """
        </div>
                <div style='margin-left:320px'>
                    <div style='w3-container'>
                        <br>
                        <h2>Dashboard</h2>
                        <p style='font-family:'Roboto', sans-serif; font-size:16px'><b>Status: """
        if (openplc_runtime.status() == "Running"):
            return_str += "<font color = '#02CC07'>Running</font></b></p>"
        else:
            return_str += "<font color = 'Red'>Stopped</font></b></p>"
            
        return_str += "<p style='font-family:'Roboto', sans-serif; font-size:16px'><b>Program:</b> " + openplc_runtime.project_name + "</p>"
        return_str += "<p style='font-family:'Roboto', sans-serif; font-size:16px'><b>Description:</b> " + openplc_runtime.project_description + "</p>"
        return_str += "<p style='font-family:'Roboto', sans-serif; font-size:16px'><b>File:</b> " + openplc_runtime.project_file + "</p>"
        return_str += "<p style='font-family:'Roboto', sans-serif; font-size:16px'><b>Runtime:</b> " + openplc_runtime.exec_time() + "</p>"
        
        return_str += pages.dashboard_tail
        
        return return_str


@app.route('/programs', methods=['GET', 'POST'])
def programs():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        monitor.stop_monitor()
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        list_all = False
        if (flask.request.args.get('list_all') == '1'):
            list_all = True
        return_str = pages.w3_style + pages.style + draw_top_div()
        return_str += """
            <div class='main'>
                <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                    <br>
                    <br>
                    <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                    <a href="programs" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/programs-icon-64x64.png" alt="Programs" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Programs</p></a>
                    <a href='modbus' class='w3-bar-item w3-button'><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></a>
                    <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                    <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                    <a href='users' class='w3-bar-item w3-button'><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></a>
                    <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                    <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                    <br>
                    <br>"""
        return_str += draw_status()
        return_str += """
        </div>
            <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>
                    <h2>Programs</h2>
                    <p>Here you can upload a new program to OpenPLC or revert back to a previous uploaded program shown on the table.</p>
                    <table>
                        <tr style='background-color: white'>
                            <th>Program Name</th><th>File</th><th>Date Uploaded</th>
                        </tr>"""
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                if (list_all == True):
                    cur.execute("SELECT Prog_ID, Name, File, Date_upload FROM Programs ORDER BY Date_upload DESC")
                else:
                    cur.execute("SELECT Prog_ID, Name, File, Date_upload FROM Programs ORDER BY Date_upload DESC LIMIT 10")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                
                for row in rows:
                    return_str += "<tr onclick=\"document.location='reload-program?table_id=" + str(row[0]) + "'\">"
                    return_str += "<td>" + str(row[1]) + "</td><td>" + str(row[2]) + "</td><td>" + time.strftime('%b %d, %Y - %I:%M%p', time.localtime(row[3])) + "</td></tr>"
                    
                return_str += """
                    </table>
                    <a href="programs?list_all=1" style="text-align:right; float:right; color:black; font-weight:bold;">List all programs</a>
                    <br>
                    <br>
                    <h2>Upload Program</h2>
                    <form   id    = "uploadForm"
                        enctype   =  "multipart/form-data"
                        action    =  "upload-program"
                        method    =  "post">
                        <br>
                        <input type="file" name="file" id="file" class="inputfile" accept=".st">
                        <input type="submit" value="Upload Program" name="submit">
                    </form>
                </div>
            </div>
        </div>
    </body>
</html>"""
            except Error as e:
                print("error connecting to the database" + str(e))
                return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
        else:
            return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'
        
        return return_str


@app.route('/reload-program', methods=['GET', 'POST'])
def reload_program():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        prog_id = flask.request.args.get('table_id')
        return_str = pages.w3_style + pages.style + draw_top_div()
        return_str += """
            <div class='main'>
                <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                    <br>
                    <br>
                    <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                    <a href="programs" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/programs-icon-64x64.png" alt="Programs" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Programs</p></a>
                    <a href='modbus' class='w3-bar-item w3-button'><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></a>
                    <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                    <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                    <a href='users' class='w3-bar-item w3-button'><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></a>
                    <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                    <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                    <br>
                    <br>"""
        return_str += draw_status()
        return_str += """
            </div>
            <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>
                    <h2>Program Info</h2>
                    <br>"""
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM Programs WHERE Prog_ID = ?", (int(prog_id),))
                row = cur.fetchone()
                cur.close()
                conn.close()
                return_str += "<label for='prog_name'><b>Name</b></label><input type='text' id='prog_name' name='program_name' value='" + str(row[1]) + "' disabled>"
                return_str += "<label for='prog_descr'><b>Description</b></label><textarea type='text' rows='10' style='resize:vertical' id='prog_descr' name='program_descr' disabled>" + str(row[2]) + "</textarea>"
                return_str += "<label for='prog_file'><b>File</b></label><input type='text' id='prog_file' name='program_file' value='" + str(row[3]) + "' disabled>"
                return_str += "<label for='prog_date'><b>Date Uploaded</b></label><input type='text' id='prog_date' name='program_date' value='" + time.strftime('%b %d, %Y - %I:%M%p', time.localtime(row[4])) + "' disabled>"
                return_str += "<br><br><center><a href='compile-program?file=" + str(row[3]) + "' class='button' style='width: 310px; height: 53px; margin: 0px 20px 0px 20px;'><b>Reload program</b></a><a href='remove-program?id=" + str(prog_id) + "' class='button' style='width: 310px; height: 53px; margin: 0px 20px 0px 20px;'><b>Remove program</b></a></center>"
                return_str += """
                </div>
            </div>
        </div>
    </body>
</html>"""

            except Error as e:
                print("error connecting to the database" + str(e))
                return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
        else:
            return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'
        
        return return_str
        
        
@app.route('/remove-program', methods=['GET', 'POST'])
def remove_program():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        prog_id = flask.request.args.get('id')
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM Programs WHERE Prog_ID = ?", (int(prog_id),))
                conn.commit()
                cur.close()
                conn.close()
                return flask.redirect(flask.url_for('programs'))
                
            except Error as e:
                print("error connecting to the database" + str(e))
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
        else:
            return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'


@app.route('/upload-program', methods=['GET', 'POST'])
def upload_program():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        if ('file' not in flask.request.files):
            return draw_blank_page() + "<h2>Error</h2><p>You need to select a file to be uploaded!<br><br>Use the back-arrow on your browser to return</p></div></div></div></body></html>"
        prog_file = flask.request.files['file']
        if (prog_file.filename == ''):
            return draw_blank_page() + "<h2>Error</h2><p>You need to select a file to be uploaded!<br><br>Use the back-arrow on your browser to return</p></div></div></div></body></html>"
        
        filename = str(random.randint(1,1000000)) + ".st"
        prog_file.save(os.path.join('../etc/st_files', filename))
        
        return_str = pages.w3_style + pages.style + draw_top_div()
        return_str += """
            <div class='main'>
                <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                    <br>
                    <br>
                    <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                    <a href="programs" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/programs-icon-64x64.png" alt="Programs" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Programs</p></a>
                    <a href='modbus' class='w3-bar-item w3-button'><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></a>
                    <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                    <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                    <a href='users' class='w3-bar-item w3-button'><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></a>
                    <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                    <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                    <br>
                    <br>"""
        return_str += draw_status()
        return_str += """
        </div>
            <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>
                    <h2>Program Info</h2>
                    <br>
                    <form id      = "uploadForm"
                        enctype   = "multipart/form-data"
                        action    = "upload-program-action"
                        method    = "post"
                        onsubmit  = "return validateForm()">
                        
                        <label for='prog_name'><b>Name</b></label>
                        <input type='text' id='prog_name' name='prog_name' placeholder='My Program v1.0'>
                        <label for='prog_descr'><b>Description</b></label>
                        <textarea type='text' rows='10' style='resize:vertical' id='prog_descr' name='prog_descr' placeholder='Insert the program description here'></textarea>"""
        return_str += "<label for='prog_file'><b>File</b></label><input type='text' id='program_file' name='program_file' value='" + filename + "' disabled>"
        return_str += "<label for='prog_date'><b>Date Uploaded</b></label><input type='text' id='prog_date' name='prog_date' value='" + time.strftime('%b %d, %Y - %I:%M%p', time.localtime(int(time.time()))) + "' disabled>"
        return_str += "<input type='hidden' value='" + filename + "' id='prog_file' name='prog_file'/>"
        return_str += "<input type='hidden' value='" + str(int(time.time())) + "' id='epoch_time' name='epoch_time'/>"
        return_str += """
                        <br>
                        <br>
                        <center><input type="submit" class="button" style="font-weight:bold; width: 310px; height: 53px; margin: 0px 20px 0px 20px;" value="Upload program"></center>
                    </form>
                </div>
            </div>
        </div>
    </body>
    
    <script type="text/javascript">
        function validateForm()
        {
            var progname = document.forms["uploadForm"]["prog_name"].value;
            if (progname == "")
            {
                alert("Program Name cannot be blank");
                return false;
            }
            return true;
        }
    </script>
</html>"""

        return return_str


@app.route('/upload-program-action', methods=['GET', 'POST'])
def upload_program_action():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        prog_name = flask.request.form['prog_name']
        prog_descr = flask.request.form['prog_descr']
        prog_file = flask.request.form['prog_file']
        epoch_time = flask.request.form['epoch_time']
        
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO Programs (Name, Description, File, Date_upload) VALUES (?, ?, ?, ?)", (prog_name, prog_descr, prog_file, epoch_time))
                conn.commit()
                cur.close()
                conn.close()
                #Redirect back to the compiling page
                return '<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0; url=/compile-program?file=' + prog_file + '"></head></html>'
            
            except Error as e:
                print("error connecting to the database" + str(e))
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
        else:
            return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'
        

@app.route('/compile-program', methods=['GET', 'POST'])
def compile_program():
    global openplc_runtime
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        st_file = flask.request.args.get('file')
        
        #load information about the program being compiled into the openplc_runtime object
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM Programs WHERE File=?", (st_file,))
                row = cur.fetchone()
                openplc_runtime.project_name = str(row[1])
                openplc_runtime.project_description = str(row[2])
                openplc_runtime.project_file = str(row[3])
                cur.close()
                conn.close()
            except Error as e:
                print("error connecting to the database" + str(e))
        else:
            print("error connecting to the database")
        
        delete_persistent_file()
        openplc_runtime.compile_program(st_file)
        
        return draw_compiling_page()


@app.route('/compilation-logs', methods=['GET', 'POST'])
def compilation_logs():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        return openplc_runtime.compilation_status()


@app.route('/modbus', methods=['GET', 'POST'])
def modbus():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        monitor.stop_monitor()
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        return_str = pages.w3_style + pages.style + draw_top_div()
        return_str += """
            <div class='main'>
                <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                    <br>
                    <br>
                    <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                    <a href="programs" class="w3-bar-item w3-button"><img src="/static/programs-icon-64x64.png" alt="Programs" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></a>
                    <a href="modbus" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/modbus-icon-512x512.png" alt="Modbus" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Slave Devices</p></a>
                    <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                    <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                    <a href='users' class='w3-bar-item w3-button'><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></a>
                    <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                    <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                    <br>
                    <br>"""
        return_str += draw_status()
        return_str += """
        </div>
            <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>
                    <h2>Slave Devices</h2>
                    <p>List of Slave devices attached to OpenPLC.</p>
                    <p><b>Attention:</b> Slave devices are attached to address 100 onward (i.e. %IX100.0, %IW100, %QX100.0, and %QW100)
                    <table>
                        <tr style='background-color: white'>
                            <th>Device Name</th><th>Device Type</th><th>DI</th><th>DO</th><th>AI</th><th>AO</th>
                        </tr>"""
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                cur.execute("SELECT dev_id, dev_name, dev_type, di_size, coil_size, ir_size, hr_read_size, hr_write_size FROM Slave_dev")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                
                counter_di = 0
                counter_do = 0
                counter_ai = 0
                counter_ao = 0
                
                for row in rows:
                    return_str += "<tr onclick=\"document.location='modbus-edit-device?table_id=" + str(row[0]) + "'\">"
                    
                    #calculate di
                    if (row[3] == 0):
                        di = "-"
                    else:
                        di = "%IX" + str(100 + (counter_di/8)) + "." + str(counter_di%8) + " to "
                        counter_di += row[3];
                        di += "%IX" + str(100 + ((counter_di-1)/8)) + "." + str((counter_di-1)%8)
                        
                    #calculate do
                    if (row[4] == 0):
                        do = "-"
                    else:
                        do = "%QX" + str(100 + (counter_do/8)) + "." + str(counter_do%8) + " to "
                        counter_do += row[4];
                        do += "%QX" + str(100 + ((counter_do-1)/8)) + "." + str((counter_do-1)%8)
                        
                    #calculate ai
                    if (row[5] + row[6] == 0):
                        ai = "-"
                    else:
                        ai = "%IW" + str(100 + counter_ai) + " to "
                        counter_ai += row[5]+row[6];
                        ai += "%IW" + str(100 + (counter_ai-1))
                        
                    #calculate ao
                    if (row[7] == 0):
                        ao = "-"
                    else:
                        ao = "%QW" + str(100 + counter_ao) + " to "
                        counter_ao += row[7];
                        ao += "%QW" + str(100 + (counter_ao-1))
                    
                    
                    return_str += "<td>" + str(row[1]) + "</td><td>" + str(row[2]) + "</td><td>" + di + "</td><td>" + do + "</td><td>" + ai + "</td><td>" + ao + "</td></tr>"
                    
                return_str += """
                    </table>
                    <br>
                    <center><a href="add-modbus-device" class="button" style="width: 310px; height: 53px; margin: 0px 20px 0px 20px;"><b>Add new device</b></a></center>
                </div>
            </div>
        </div>
    </body>
</html>"""

            except Error as e:
                print("error connecting to the database" + str(e))
                return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
        else:
            return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'
        
        return return_str
        

@app.route('/add-modbus-device', methods=['GET', 'POST'])
def add_modbus_device():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        if (flask.request.method == 'GET'):
            return_str = pages.w3_style + pages.style + draw_top_div()
            return_str += """
                <div class='main'>
                    <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                        <br>
                        <br>
                        <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                        <a href="programs" class="w3-bar-item w3-button"><img src="/static/programs-icon-64x64.png" alt="Programs" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></a>
                        <a href="modbus" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/modbus-icon-512x512.png" alt="Modbus" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Slave Devices</p></a>
                        <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                        <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                        <a href='users' class='w3-bar-item w3-button'><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></a>
                        <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                        <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                        <br>
                        <br>"""
            return_str += draw_status()
            return_str += """
                </div>
                <div style="margin-left:320px; margin-right:70px">
                    <div style="w3-container">
                        <br>
                        <h2>Add new device</h2>
                        <br>
                        <div style="float:left; width:45%; height:730px">
                        <form   id    = "uploadForm"
                            enctype   =  "multipart/form-data"
                            action    =  "add-modbus-device"
                            method    =  "post"
                            onsubmit  =  "return validateForm()">
                            <label for='dev_name'><b>Device Name</b></label>
                            <input type='text' id='dev_name' name='device_name' placeholder='My Device'>
                            <label for='dev_protocol'><b>Device Type</b></label>
                            <select id='dev_protocol' name='device_protocol'>
                                <option selected='selected' value='Uno'>Arduino Uno</option>
                                <option value='Mega'>Arduino Mega</option>
                                <option value='ESP32'>ESP32</option>
                                <option value='ESP8266'>ESP8266</option>
                                <option value='TCP'>Generic Modbus TCP Device</option>
                                <option value='RTU'>Generic Modbus RTU Device</option>
                            </select>
                            <label for='dev_id'><b>Slave ID</b></label>
                            <input type='text' id='dev_id' name='device_id' placeholder='0'>
                            <div id="tcp-stuff" style="display: none">
                            <label for='dev_ip'><b>IP Address</b></label>
                            <input type='text' id='dev_ip' name='device_ip' placeholder='192.168.0.1'>
                            <label for='dev_port'><b>IP Port</b></label>
                            <input type='text' id='dev_port' name='device_port' placeholder='502'>
                            </div>
                            <div id="rtu-stuff">
                            <label for='dev_cport'><b>COM Port</b></label>
                            <select id='dev_cport' name='device_cport'>"""
                            
            ports = [comport.device for comport in serial.tools.list_ports.comports()]
            for port in ports:
                if (platform.system().startswith("CYGWIN")):
                    port_name = "COM" + str(int(port.split("/dev/ttyS")[1]) + 1)
                else:
                    port_name = port
                return_str += "<option value='" + port_name + "'>" + port_name + "</option>"
            
            return_str += pages.add_slave_devices_tail + pages.add_devices_script
            
            return return_str
            
        elif (flask.request.method == 'POST'):
            devname = flask.request.form.get('device_name')
            devtype = flask.request.form.get('device_protocol')
            devid = flask.request.form.get('device_id')
            devip = flask.request.form.get('device_ip')
            devport = flask.request.form.get('device_port')
            devcport = flask.request.form.get('device_cport')
            devbaud = flask.request.form.get('device_baud')
            devparity = flask.request.form.get('device_parity')
            devdata = flask.request.form.get('device_data')
            devstop = flask.request.form.get('device_stop')
            
            di_start = flask.request.form.get('di_start')
            di_size = flask.request.form.get('di_size')
            do_start = flask.request.form.get('do_start')
            do_size = flask.request.form.get('do_size')
            ai_start = flask.request.form.get('ai_start')
            ai_size = flask.request.form.get('ai_size')
            aor_start = flask.request.form.get('aor_start')
            aor_size = flask.request.form.get('aor_size')
            aow_start = flask.request.form.get('aow_start')
            aow_size = flask.request.form.get('aow_size')
            
            database = "../etc/openplc.db"
            conn = create_connection(database)
            if (conn != None):
                try:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO Slave_dev (dev_name, dev_type, slave_id, com_port, baud_rate, parity, data_bits, stop_bits, ip_address, ip_port, di_start, di_size, coil_start, coil_size, ir_start, ir_size, hr_read_start, hr_read_size, hr_write_start, hr_write_size) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (devname, devtype, devid, devcport, devbaud, devparity, devdata, devstop, devip, devport, di_start, di_size, do_start, do_size, ai_start, ai_size, aor_start, aor_size, aow_start, aow_size))
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    generate_mbconfig()
                    return flask.redirect(flask.url_for('modbus'))
                    
                except Error as e:
                    print("error connecting to the database" + str(e))
                    return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
            else:
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'


@app.route('/modbus-edit-device', methods=['GET', 'POST'])
def modbus_edit_device():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        if (flask.request.method == 'GET'):
            dev_id = flask.request.args.get('table_id')
            return_str = pages.w3_style + pages.style + draw_top_div()
            return_str += """
                <div class='main'>
                    <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                        <br>
                        <br>
                        <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                        <a href="programs" class="w3-bar-item w3-button"><img src="/static/programs-icon-64x64.png" alt="Programs" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></a>
                        <a href="modbus" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/modbus-icon-512x512.png" alt="Modbus" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Slave Devices</p></a>
                        <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                        <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                        <a href='users' class='w3-bar-item w3-button'><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></a>
                        <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                        <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                        <br>
                        <br>"""
            return_str += draw_status()
            return_str += """
                </div>
                <div style="margin-left:320px; margin-right:70px">
                    <div style="w3-container">
                        <br>
                        <h2>Edit slave device</h2>
                        <br>
                        <div style="float:left; width:45%; height:730px">
                        <form   id    = "uploadForm"
                            enctype   =  "multipart/form-data"
                            action    =  "modbus-edit-device"
                            method    =  "post"
                            onsubmit  =  "return validateForm()">"""
                            
            database = "../etc/openplc.db"
            conn = create_connection(database)
            if (conn != None):
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM Slave_dev WHERE dev_id = ?", (int(dev_id),))
                    row = cur.fetchone()
                    cur.close()
                    conn.close()
                    return_str += "<input type='hidden' value='" + dev_id + "' id='db_dev_id' name='db_dev_id'/>"
                    return_str += "<label for='dev_name'><b>Device Name</b></label><input type='text' id='dev_name' name='device_name' placeholder='My Device' value='" + str(row[1]) + "'>"
                    return_str += "<label for='dev_protocol'><b>Device Type</b></label><select id='dev_protocol' name='device_protocol'>"
                    if (str(row[2]) == "Uno"):
                        return_str += "<option selected='selected' value='Uno'>Arduino Uno</option>"
                    else:
                        return_str += "<option value='Uno'>Arduino Uno</option>"
                    if (str(row[2]) == "Mega"):
                        return_str += "<option selected='selected' value='Mega'>Arduino Mega</option>"
                    else:
                        return_str += "<option value='Mega'>Arduino Mega</option>"
                    if (str(row[2]) == "ESP32"):
                        return_str += "<option selected='selected' value='ESP32'>ESP32</option>"
                    else:
                        return_str += "<option value='ESP32'>ESP32</option>"
                    if (str(row[2]) == "ESP8266"):
                        return_str += "<option selected='selected' value='ESP8266'>ESP8266</option>"
                    else:
                        return_str += "<option value='ESP8266'>ESP8266</option>"
                    if (str(row[2]) == "TCP"):
                        return_str += "<option selected='selected' value='TCP'>Generic Modbus TCP Device</option>"
                    else:
                        return_str += "<option value='TCP'>Generic Modbus TCP Device</option>"
                    if (str(row[2]) == "RTU"):
                        return_str += "<option selected='selected' value='RTU'>Generic Modbus RTU Device</option></select>"
                    else:
                        return_str += "<option value='RTU'>Generic Modbus RTU Device</option></select>"
                    return_str += "<label for='dev_id'><b>Slave ID</b></label><input type='text' id='dev_id' name='device_id' placeholder='0' value='" + str(row[3]) + "'>"
                    return_str += "<div id=\"tcp-stuff\" style=\"display: none\"><label for='dev_ip'><b>IP Address</b></label><input type='text' id='dev_ip' name='device_ip' placeholder='192.168.0.1' value='" + str(row[9]) + "'>"
                    return_str += "<label for='dev_port'><b>IP Port</b></label><input type='text' id='dev_port' name='device_port' placeholder='502' value='" + str(row[10]) + "'></div>"
                    return_str += "<div id=\"rtu-stuff\"><label for='dev_cport'><b>COM Port</b></label><select id='dev_cport' name='device_cport'>"
                    ports = [comport.device for comport in serial.tools.list_ports.comports()]
                    for port in ports:
                        if (platform.system().startswith("CYGWIN")):
                            port_name = "COM" + str(int(port.split("/dev/ttyS")[1]) + 1)
                        else:
                            port_name = port
                        if (str(row[4]) == port_name):
                            return_str += "<option selected='selected' value'" + port_name + "'>" + port_name + "</option>"
                        else:   
                            return_str += "<option value='" + port_name + "'>" + port_name + "</option>"
                    
                    return_str += pages.edit_slave_devices_tail
                    return_str += dev_id
                    return_str += """' class="button" style="width: 310px; height: 53px; margin: 0px 20px 0px 20px;"><b>Delete device</b></a></center>
                    </form>
                </div>
            </div>
        </div>
    </body>"""
                    return_str += pages.edit_devices_script
                    return_str += 'devid.value = "' + str(row[3]) + '";'
                    return_str += 'devcport.value = "' + str(row[4]) + '";'
                    return_str += 'devbaud.value = "' + str(row[5]) + '";'
                    return_str += 'devparity.value = "' + str(row[6]) + '";'
                    return_str += 'devdata.value = "' + str(row[7]) + '";'
                    return_str += 'devstop.value = "' + str(row[8]) + '";'
                    return_str += 'devip.value = "' + str(row[9]) + '";'
                    return_str += 'devport.value = "' + str(row[10]) + '";'
                    return_str += 'distart.value = "' + str(row[11]) + '";'
                    return_str += 'disize.value = "' + str(row[12]) + '";'
                    return_str += 'dostart.value = "' + str(row[13]) + '";'
                    return_str += 'dosize.value = "' + str(row[14]) + '";'
                    return_str += 'aistart.value = "' + str(row[15]) + '";'
                    return_str += 'aisize.value = "' + str(row[16]) + '";'
                    return_str += 'aorstart.value = "' + str(row[17]) + '";'
                    return_str += 'aorsize.value = "' + str(row[18]) + '";'
                    return_str += 'aowstart.value = "' + str(row[19]) + '";'
                    return_str += 'aowsize.value = "' + str(row[20]) + '";}</script></html>'
                    
                except Error as e:
                    print("error connecting to the database" + str(e))
                    return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
            else:
                return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'
            
            return return_str
            
        elif (flask.request.method == 'POST'):
            devid_db = flask.request.form.get('db_dev_id')
            devname = flask.request.form.get('device_name')
            devtype = flask.request.form.get('device_protocol')
            devid = flask.request.form.get('device_id')
            devip = flask.request.form.get('device_ip')
            devport = flask.request.form.get('device_port')
            devcport = flask.request.form.get('device_cport')
            devbaud = flask.request.form.get('device_baud')
            devparity = flask.request.form.get('device_parity')
            devdata = flask.request.form.get('device_data')
            devstop = flask.request.form.get('device_stop')
            
            di_start = flask.request.form.get('di_start')
            di_size = flask.request.form.get('di_size')
            do_start = flask.request.form.get('do_start')
            do_size = flask.request.form.get('do_size')
            ai_start = flask.request.form.get('ai_start')
            ai_size = flask.request.form.get('ai_size')
            aor_start = flask.request.form.get('aor_start')
            aor_size = flask.request.form.get('aor_size')
            aow_start = flask.request.form.get('aow_start')
            aow_size = flask.request.form.get('aow_size')
            
            database = "../etc/openplc.db"
            conn = create_connection(database)
            if (conn != None):
                try:
                    cur = conn.cursor()
                    cur.execute("UPDATE Slave_dev SET dev_name = ?, dev_type = ?, slave_id = ?, com_port = ?, baud_rate = ?, parity = ?, data_bits = ?, stop_bits = ?, ip_address = ?, ip_port = ?, di_start = ?, di_size = ?, coil_start = ?, coil_size = ?, ir_start = ?, ir_size = ?, hr_read_start = ?, hr_read_size = ?, hr_write_start = ?, hr_write_size = ? WHERE dev_id = ?", (devname, devtype, devid, devcport, devbaud, devparity, devdata, devstop, devip, devport, di_start, di_size, do_start, do_size, ai_start, ai_size, aor_start, aor_size, aow_start, aow_size, int(devid_db)))
                    conn.commit()
                    cur.close()
                    conn.close()
                    
                    generate_mbconfig()
                    return flask.redirect(flask.url_for('modbus'))
                    
                except Error as e:
                    print("error connecting to the database" + str(e))
                    return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
            else:
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'


@app.route('/delete-device', methods=['GET', 'POST'])
def delete_device():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        devid_db = flask.request.args.get('dev_id')
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM Slave_dev WHERE dev_id = ?", (int(devid_db),))
                conn.commit()
                cur.close()
                conn.close()
                generate_mbconfig()
                return flask.redirect(flask.url_for('modbus'))
            except Error as e:
                print("error connecting to the database" + str(e))
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
        else:
            return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'

            
@app.route('/monitoring', methods=['GET', 'POST'])
def monitoring():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        return_str = pages.w3_style + pages.monitoring_head + draw_top_div()
        return_str += """
            <div class='main'>
                <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                    <br>
                    <br>
                    <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                    <a href='programs' class='w3-bar-item w3-button'><img src='/static/programs-icon-64x64.png' alt='Programs' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></a>
                    <a href='modbus' class='w3-bar-item w3-button'><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></a>
                    <a href="monitoring" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/monitoring-icon-64x64.png" alt="Monitoring" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Monitoring</p></a>                    
                    <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                    <a href='users' class='w3-bar-item w3-button'><img src='/static/users-icon-64x64.png' alt='Users' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Users</p></a>
                    <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                    <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                    <br>
                    <br>"""
        return_str += draw_status()
        return_str += """
        </div>
            <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>
                    <h2>Monitoring</h2>
                    <p>The table below displays a list of the OpenPLC points used by the currently running program. By clicking in one of the listed points it is possible to see more information about it and also to force it to be a different value.</p>
                    <div id='monitor_table'>
                        <table>
                            <col width="50"><col width="10"><col width="10"><col width="10"><col width="100">
                            <tr style='background-color: white'>
                                <th>Point Name</th><th>Type</th><th>Location</th><th>Forced</th><th>Value</th>
                            </tr>"""
        
        if (openplc_runtime.status() == "Running"):
            monitor.start_monitor()
            data_index = 0
            for debug_data in monitor.debug_vars:
                return_str += '<tr style="height:60px" onclick="document.location=\'point-info?table_id=' + str(data_index) + '\'">'
                return_str += '<td>' + debug_data.name + '</td><td>' + debug_data.type + '</td><td>' + debug_data.location + '</td><td>' + debug_data.forced + '</td><td valign="middle">'
                if (debug_data.type == 'BOOL'):
                    if (debug_data.value == 0):
                        return_str += '<img src="/static/bool_false.png" alt="bool_false" style="width:40px;height:40px;vertical-align:middle; margin-right:10px">FALSE</td>'
                    else:
                        return_str += '<img src="/static/bool_true.png" alt="bool_true" style="width:40px;height:40px;vertical-align:middle; margin-right:10px">TRUE</td>'
                else:
                    percentage = (debug_data.value*100)/65535
                    return_str += '<div class="w3-grey w3-round" style="height:40px"><div class="w3-container w3-blue w3-round" style="height:40px;width:' + str(int(percentage)) + '%"><p style="margin-top:10px">' + str(debug_data.value) + '</p></div></div></td>'
                return_str += '</tr>'
                data_index += 1
            return_str += pages.monitoring_tail
        
        else:
            return_str += """
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </body>
</html>"""

        return return_str
        
@app.route('/monitor-update', methods=['GET', 'POST'])
def monitor_update():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        #if (openplc_runtime.status() == "Compiling"): return 'OpenPLC is compiling new code. Please wait'
        return_str = """
                        <table>
                            <col width="50"><col width="10"><col width="10"><col width="10"><col width="100">
                            <tr style='background-color: white'>
                                <th>Point Name</th><th>Type</th><th>Location</th><th>Forced</th><th>Value</th>
                            </tr>"""
        
        #if (openplc_runtime.status() == "Running"):
        if (True):
            monitor.start_monitor()
            data_index = 0
            for debug_data in monitor.debug_vars:
                return_str += '<tr style="height:60px" onclick="document.location=\'point-info?table_id=' + str(data_index) + '\'">'
                return_str += '<td>' + debug_data.name + '</td><td>' + debug_data.type + '</td><td>' + debug_data.location + '</td><td>' + debug_data.forced + '</td><td valign="middle">'
                if (debug_data.type == 'BOOL'):
                    if (debug_data.value == 0):
                        return_str += '<img src="/static/bool_false.png" alt="bool_false" style="width:40px;height:40px;vertical-align:middle; margin-right:10px">FALSE</td>'
                    else:
                        return_str += '<img src="/static/bool_true.png" alt="bool_true" style="width:40px;height:40px;vertical-align:middle; margin-right:10px">TRUE</td>'
                else:
                    percentage = (debug_data.value*100)/65535
                    return_str += '<div class="w3-grey w3-round" style="height:40px"><div class="w3-container w3-blue w3-round" style="height:40px;width:' + str(int(percentage)) + '%"><p style="margin-top:10px">' + str(debug_data.value) + '</p></div></div></td>'
                return_str += '</tr>'
                data_index += 1
        
        return_str += """ 
                        </table>"""
        
        return return_str
            
            
@app.route('/hardware', methods=['GET', 'POST'])
def hardware():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        monitor.stop_monitor()
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        if (flask.request.method == 'GET'):
            driver_path = os.path.abspath(os.path.join(self_path, '..', 'etc', 'openplc_driver'))
            with open(driver_path) as f: current_driver = f.read().rstrip()
            return_str = pages.w3_style + pages.hardware_style + draw_top_div() + pages.hardware_head
            return_str += draw_status()
            return_str += """
            </div>
            <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>
                    <h2>Hardware</h2>
                    <p>OpenPLC controls inputs and outputs through a piece of code called hardware layer (also known as driver). Therefore, to properly handle the inputs and outputs of your board, you must select the appropriate hardware layer for it. The Blank hardware layer is the default option on OpenPLC, which provides no support for native inputs and outputs.</p>
                    <!-- <p>This section allows you to change the hardware layer used by OpenPLC. It is also possible to augment the current hardware layer through the hardware layer code box. -->
                    <p><b>OpenPLC Hardware Layer</b><p>
                    <form   id    = "uploadForm"
                        enctype   =  "multipart/form-data"
                        action    =  "hardware"
                        method    =  "post">
                        <select id='hardware_layer' name='hardware_layer' style="width:400px;height:30px;font-size: 16px;font-family: 'Roboto', sans-serif;">"""
            if (current_driver == "blank"): return_str += "<option selected='selected' value='blank'>Blank</option>"
            else: return_str += "<option value='blank'>Blank</option>"
            if (current_driver == "blank_linux"): return_str += "<option selected='selected' value='blank_linux'>Blank Linux</option>"
            else: return_str += "<option value='blank_linux'>Blank with DNP3 (Linux only)</option>"
            if (current_driver == "fischertechnik"): return_str += "<option selected='selected' value='fischertechnik'>Fischertechnik</option>"
            else: return_str += "<option value='fischertechnik'>Fischertechnik</option>"
            if (current_driver == "neuron"): return_str += "<option selected='selected' value='neuron'>Neuron</option>"
            else: return_str += "<option value='neuron'>Neuron</option>"
            if (current_driver == "pixtend"): return_str += "<option selected='selected' value='pixtend'>PiXtend</option>"
            else: return_str += "<option value='pixtend'>PiXtend</option>"
            if (current_driver == "pixtend_2s"): return_str += "<option selected='selected' value='pixtend_2s'>PiXtend 2s</option>"
            else: return_str += "<option value='pixtend_2s'>PiXtend 2s</option>"
            if (current_driver == "pixtend_2l"): return_str += "<option selected='selected' value='pixtend_2l'>PiXtend 2l</option>"
            else: return_str += "<option value='pixtend_2l'>PiXtend 2l</option>"  
            if (current_driver == "rpi"): return_str += "<option selected='selected' value='rpi'>Raspberry Pi</option>"
            else: return_str += "<option value='rpi'>Raspberry Pi</option>"
            if (current_driver == "rpi_old"): return_str += "<option selected='selected' value='rpi_old'>Raspberry Pi - Old Model (2011 model B)</option>"
            else: return_str += "<option value='rpi_old'>Raspberry Pi - Old Model (2011 model B)</option>"
            if (current_driver == "simulink"): return_str += "<option selected='selected' value='simulink'>Simulink</option>"
            else: return_str += "<option value='simulink'>Simulink</option>"
            if (current_driver == "simulink_linux"): return_str += "<option selected='selected' value='simulink_linux'>Simulink with DNP3 (Linux only)</option>"
            else: return_str += "<option value='simulink_linux'>Simulink with DNP3 (Linux only)</option>"
            if (current_driver == "unipi"): return_str += "<option selected='selected' value='unipi'>UniPi v1.1</option>"
            else: return_str += "<option value='unipi'>UniPi v1.1</option>"
            return_str += """
                        </select>
                        <br>
                        <br>
                        <p><b>Hardware Layer Code Box</b><p>
                        <p>The Hardware Layer Code Box allows you to extend the functionality of the current driver by adding custom code to it, such as reading I2C, SPI and 1-Wire sensors, or controling port expanders to add more outputs to your hardware</p>
                        <textarea wrap="off" spellcheck="false" name="custom_layer_code" id="custom_layer_code">"""
            with open('../runtime/core/custom_layer.h') as f: return_str += f.read()
            return_str += pages.hardware_tail
            
        else:
            hardware_layer = flask.request.form['hardware_layer']
            custom_layer_code = flask.request.form['custom_layer_code']
            program_dir = os.path.abspath(os.path.join(self_path, '..', 'etc', 'active_program'))
            with open(program_dir) as f: current_program = f.read()
            with open('../runtime/core/custom_layer.h', 'w+') as f: f.write(custom_layer_code)
            
            scripts_path = os.path.abspath(os.path.join(self_path, '..', 'scripts'))
            change_hardware_path = os.path.join(scripts_path, 'change_hardware_layer.sh')
            subprocess.call([change_hardware_path, hardware_layer], cwd=scripts_path)
            return "<head><meta http-equiv=\"refresh\" content=\"0; URL='compile-program?file=" + current_program + "'\" /></head>"
        
        return return_str


@app.route('/restore_custom_hardware')
def restore_custom_hardware():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        
        #Restore the original custom layer code
        with open('../runtime/core/custom_layer.original') as f: original_code = f.read()
        with open('../runtime/core/custom_layer.h', 'w+') as f: f.write(original_code)
        return flask.redirect(flask.url_for('hardware'))
        

@app.route('/users')
def users():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        monitor.stop_monitor()
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        return_str = pages.w3_style + pages.style + draw_top_div()
        return_str += """
            <div class='main'>
                <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                    <br>
                    <br>
                    <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                    <a href='programs' class='w3-bar-item w3-button'><img src='/static/programs-icon-64x64.png' alt='Programs' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></a>
                    <a href='modbus' class='w3-bar-item w3-button'><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></a>
                    <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                    <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                    <a href="users" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/users-icon-64x64.png" alt="Users" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Users</p></a>
                    <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                    <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                    <br>
                    <br>"""
        return_str += draw_status()
        return_str += """
            </div>
            <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>
                    <h2>Users</h2>
                    <br>
                    <table>
                        <tr style='background-color: white'>
                            <th>Full Name</th><th>Username</th><th>Email</th>
                        </tr>"""
        
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                cur.execute("SELECT user_id, name, username, email FROM Users")
                rows = cur.fetchall()
                cur.close()
                conn.close()
                
                for row in rows:
                    return_str += "<tr onclick=\"document.location='edit-user?table_id=" + str(row[0]) + "'\">"
                    return_str += "<td>" + str(row[1]) + "</td><td>" + str(row[2]) + "</td><td>" + str(row[3]) + "</td></tr>"
                
                return_str += """
                </table>
                    <br>
                    <center><a href="add-user" class="button" style="width: 310px; height: 53px; margin: 0px 20px 0px 20px;"><b>Add new user</b></a></center>
                </div>
            </div>
        </div>
    </body>
</html>"""
            except Error as e:
                print("error connecting to the database" + str(e))
                return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
        else:
            return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'
        
        return return_str


@app.route('/add-user', methods=['GET', 'POST'])
def add_user():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        if (flask.request.method == 'GET'):
            return_str = pages.w3_style + pages.style + draw_top_div()
            return_str += """
                <div class='main'>
                    <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                        <br>
                        <br>
                        <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                        <a href='programs' class='w3-bar-item w3-button'><img src='/static/programs-icon-64x64.png' alt='Programs' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></a>
                        <a href='modbus' class='w3-bar-item w3-button'><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></a>
                        <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                        <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                        <a href="users" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/users-icon-64x64.png" alt="Users" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Users</p></a>
                        <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                        <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                        <br>
                        <br>"""
            return_str += draw_status() + pages.add_user_tail
            return return_str
            
        elif (flask.request.method == 'POST'):
            name = flask.request.form['full_name']
            username = flask.request.form['user_name']
            email = flask.request.form['user_email']
            password = flask.request.form['user_password']
            form_has_picture = True
            if ('file' not in flask.request.files):
                form_has_picture = False
            
            database = "../etc/openplc.db"
            conn = create_connection(database)
            if (conn != None):
                try:
                    cur = conn.cursor()
                    if (form_has_picture):
                        pict_file = flask.request.files['file']
                        if (pict_file.filename != ''):
                            file_extension = pict_file.filename.split('.')
                            filename = str(random.randint(1,1000000)) + "." + file_extension[-1]
                            pict_file.save(os.path.join('static', filename))
                            cur.execute("INSERT INTO Users (name, username, email, password, pict_file) VALUES (?, ?, ?, ?, ?)", (name, username, email, password, "/static/"+filename))
                        else:
                            cur.execute("INSERT INTO Users (name, username, email, password) VALUES (?, ?, ?, ?)", (name, username, email, password))
                    else:
                        cur.execute("INSERT INTO Users (name, username, email, password) VALUES (?, ?, ?, ?)", (name, username, email, password))
                    conn.commit()
                    cur.close()
                    conn.close()
                    return flask.redirect(flask.url_for('users'))
                    
                except Error as e:
                    print("error connecting to the database" + str(e))
                    return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
            else:
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'


@app.route('/edit-user', methods=['GET', 'POST'])
def edit_user():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        if (flask.request.method == 'GET'):
            user_id = flask.request.args.get('table_id')
            return_str = pages.w3_style + pages.style + draw_top_div()
            return_str += """
                <div class='main'>
                    <div class='w3-sidebar w3-bar-block' style='width:250px; background-color:#3D3D3D'>
                        <br>
                        <br>
                        <a href="dashboard" class="w3-bar-item w3-button"><img src="/static/home-icon-64x64.png" alt="Dashboard" style="width:47px;height:32px;padding:0px 15px 0px 0px;float:left"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Dashboard</p></a>
                        <a href='programs' class='w3-bar-item w3-button'><img src='/static/programs-icon-64x64.png' alt='Programs' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Programs</p></a>
                        <a href='modbus' class='w3-bar-item w3-button'><img src='/static/modbus-icon-512x512.png' alt='Modbus' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Slave Devices</p></a>
                        <a href='monitoring' class='w3-bar-item w3-button'><img src='/static/monitoring-icon-64x64.png' alt='Monitoring' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Monitoring</p></a>
                        <a href='hardware' class='w3-bar-item w3-button'><img src='/static/hardware-icon-980x974.png' alt='Hardware' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Hardware</p></a>
                        <a href="users" class="w3-bar-item w3-button" style="background-color:#E02222; padding-right:0px;padding-top:0px;padding-bottom:0px"><img src="/static/users-icon-64x64.png" alt="Users" style="width:47px;height:39px;padding:7px 15px 0px 0px;float:left"><img src="/static/arrow.png" style="width:17px;height:49px;padding:0px 0px 0px 0px;margin: 0px 0px 0px 0px; float:right"><p style='font-family:"Roboto", sans-serif; font-size:20px; color:white;margin: 10px 0px 0px 0px'>Users</p></a>
                        <a href='settings' class='w3-bar-item w3-button'><img src='/static/settings-icon-64x64.png' alt='Settings' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Settings</p></a>
                        <a href='logout' class='w3-bar-item w3-button'><img src='/static/logout-icon-64x64.png' alt='Logout' style='width:47px;height:32px;padding:0px 15px 0px 0px;float:left'><p style='font-family:\"Roboto\", sans-serif; font-size:20px; color:white;margin: 2px 0px 0px 0px'>Logout</p></a>
                        <br>
                        <br>"""
            return_str += draw_status()
            return_str += """
                </div>
                <div style="margin-left:320px; margin-right:70px">
                    <div style="w3-container">
                        <br>
                        <h2>Edit User</h2>
                        <br>
                        <form   id    = "uploadForm"
                            enctype   =  "multipart/form-data"
                            action    =  "edit-user"
                            method    =  "post"
                            onsubmit  =  "return validateForm()">"""
                        
            database = "../etc/openplc.db"
            conn = create_connection(database)
            if (conn != None):
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM Users WHERE user_id = ?", (int(user_id),))
                    row = cur.fetchone()
                    cur.close()
                    conn.close()
                    return_str += "<input type='hidden' value='" + user_id + "' id='user_id' name='user_id'/>" 
                    return_str += "<label for='full_name'><b>Name</b></label><input type='text' id='full_name' name='full_name' value='" + str(row[1]) + "'>"
                    return_str += "<label for='user_name'><b>Username</b></label><input type='text' id='user_name' name='user_name' value='" + str(row[2]) + "'>"
                    return_str += "<label for='user_email'><b>Email</b></label><input type='text' id='user_email' name='user_email' value='" + str(row[3]) + "'>"
                    return_str += """
                            <label for='user_password'><b>Password</b></label>
                            <input type='password' id='user_password' name='user_password' value='mypasswordishere'>
                            <label for='uploadForm'><b>Picture</b></label>
                            <br>
                            <br>
                            <input type="file" name="file" id="file" class="inputfile" accept="image/*">
                            <br>
                            <br>
                            <center><input type="submit" class="button" style="font-weight:bold; width: 310px; height: 53px; margin: 0px 20px 0px 20px;" value='Save changes'><a href='delete-user?user_id="""
                    return_str += user_id
                    return_str += """' class="button" style="width: 310px; height: 53px; margin: 0px 20px 0px 20px;"><b>Delete user</b></a></center>
                        </form>
                    </div>
                </div>
            </div>
        </body>
    <script>
        function validateForm()
        {
            var username = document.forms["uploadForm"]["user_name"].value;
            var password = document.forms["uploadForm"]["user_password"].value;
            if (username == "" || password == "")
            {
                alert("Username and Password cannot be blank");
                return false;
            }
            return true;
        }
    </script>
</html>"""
                except Error as e:
                    print("error connecting to the database" + str(e))
                    return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
            else:
                return_str += 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'
            
            return return_str
            
        elif (flask.request.method == 'POST'):
            user_id = flask.request.form['user_id']
            name = flask.request.form['full_name']
            username = flask.request.form['user_name']
            email = flask.request.form['user_email']
            password = flask.request.form['user_password']
            form_has_picture = True
            if ('file' not in flask.request.files):
                form_has_picture = False
            
            database = "../etc/openplc.db"
            conn = create_connection(database)
            if (conn != None):
                try:
                    cur = conn.cursor()
                    if (password != "mypasswordishere"):
                        cur.execute("UPDATE Users SET name = ?, username = ?, email = ?, password = ? WHERE user_id = ?", (name, username, email, password, int(user_id)))
                    else:
                        cur.execute("UPDATE Users SET name = ?, username = ?, email = ? WHERE user_id = ?", (name, username, email, int(user_id)))
                    conn.commit()
                    if (form_has_picture):
                        pict_file = flask.request.files['file']
                        if (pict_file.filename != ''):
                            file_extension = pict_file.filename.split('.')
                            filename = str(random.randint(1,1000000)) + "." + file_extension[-1]
                            pict_file.save(os.path.join('static', filename))
                            cur.execute("UPDATE Users SET pict_file = ? WHERE user_id = ?", ("/static/"+filename, int(user_id)))
                            conn.commit()
                    cur.close()
                    conn.close()
                    return flask.redirect(flask.url_for('users'))
                    
                except Error as e:
                    print("error connecting to the database" + str(e))
                    return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
            else:
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'


@app.route('/delete-user', methods=['GET', 'POST'])
def delete_user():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        user_id = flask.request.args.get('user_id')
        database = "../etc/openplc.db"
        conn = create_connection(database)
        if (conn != None):
            try:
                cur = conn.cursor()
                cur.execute("SELECT username FROM Users WHERE user_id = ?", (int(user_id),))
                row = cur.fetchone()
                if (flask_login.current_user.id == row[0]):
                    cur.close()
                    conn.close()
                    return draw_blank_page() + "<h2>Error</h2><p>You cannot delete yourself!<br><br>Use the back-arrow on your browser to return</p></div></div></div></body></html>"
                else:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM Users WHERE user_id = ?", (int(user_id),))
                    conn.commit()
                    cur.close()
                    conn.close()
                    return flask.redirect(flask.url_for('users'))
            except Error as e:
                print("error connecting to the database" + str(e))
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
        else:
            return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        monitor.stop_monitor()
        if (openplc_runtime.status() == "Compiling"): return draw_compiling_page()
        if (flask.request.method == 'GET'):
            return_str = pages.w3_style + pages.settings_style + draw_top_div() + pages.settings_head
            return_str += draw_status()
            return_str += """
            </div>
            <div style="margin-left:320px; margin-right:70px">
                <div style="w3-container">
                    <br>
                    <h2>Settings</h2>
                    <form id        = "uploadForm"
                        enctype     = "multipart/form-data"
                        action      = "settings"
                        method      = "post"
                        onsubmit    = "return validateForm()">
                        
                        <label class="container">
                            <b>Enable Modbus Server</b>"""
            
            database = "../etc/openplc.db"
            conn = create_connection(database)
            if (conn != None):
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM Settings")
                    rows = cur.fetchall()
                    cur.close()
                    conn.close()
                    
                    for row in rows:
                        if (row[0] == "Modbus_port"):
                            modbus_port = str(row[1])
                        elif (row[0] == "Dnp3_port"):
                            dnp3_port = str(row[1])
                        elif (row[0] == "Enip_port"):
                            enip_port = str(row[1])
                        elif (row[0] == "Pstorage_polling"):
                            pstorage_poll = str(row[1])
                        elif (row[0] == "Start_run_mode"):
                            start_run = str(row[1])
                        elif (row[0] == "Slave_polling"):
                            slave_polling = str(row[1])
                        elif (row[0] == "Slave_timeout"):
                            slave_timeout = str(row[1])
                    
                    if (modbus_port == 'disabled'):
                        return_str += """
                            <input id="modbus_server" type="checkbox">
                            <span class="checkmark"></span>
                        </label>
                        <label for='modbus_server_port'><b>Modbus Server Port</b></label>
                        <input type='text' id='modbus_server_port' name='modbus_server_port' value='502'>"""
                    else:
                        return_str += """
                            <input id="modbus_server" type="checkbox" checked>
                            <span class="checkmark"></span>
                        </label>
                        <label for='modbus_server_port'><b>Modbus Server Port</b></label>
                        <input type='text' id='modbus_server_port' name='modbus_server_port' value='""" + modbus_port + "'>"
                        
                    return_str += """
                        <br>
                        <br>
                        <br>
                        <label class="container">
                            <b>Enable DNP3 Server</b>"""
                    
                    if (dnp3_port == 'disabled'):
                        return_str += """
                            <input id="dnp3_server" type="checkbox">
                            <span class="checkmark"></span>
                        </label>
                        <label for='dnp3_server_port'><b>DNP3 Server Port</b></label>
                        <input type='text' id='dnp3_server_port' name='dnp3_server_port' value='20000'>"""
                    else:
                        return_str += """
                            <input id="dnp3_server" type="checkbox" checked>
                            <span class="checkmark"></span>
                        </label>
                        <label for='dnp3_server_port'><b>DNP3 Server Port</b></label>
                        <input type='text' id='dnp3_server_port' name='dnp3_server_port' value='""" + dnp3_port + "'>"
                    
                    return_str += """
                        <br>
                        <br>
                        <br>
                        <label class="container">
                            <b>Enable EtherNet/IP Server</b>"""
                            
                    if (enip_port == 'disabled'):
                        return_str += """
                            <input id="enip_server" type="checkbox">
                            <span class="checkmark"></span>
                        </label>
                        <label for='enip_server_port'><b>EtherNet/IP Server Port</b></label>
                        <input type='text' id='enip_server_port' name='enip_server_port' value='44818'>"""
                    else:
                        return_str += """
                            <input id="enip_server" type="checkbox" checked>
                            <span class="checkmark"></span>
                        </label>
                        <label for='enip_server_port'><b>EtherNet/IP Server Port</b></label>
                        <input type='text' id='enip_server_port' name='enip_server_port' value='""" + enip_port + "'>"
                    
                    return_str += """
                        <br>
                        <br>
                        <br>
                        <label class="container">
                            <b>Enable Persistent Storage Thread</b>"""
                            
                    if (pstorage_poll == 'disabled'):
                        return_str += """
                            <input id="pstorage_thread" type="checkbox">
                            <span class="checkmark"></span>
                        </label>
                        <label for='pstorage_thread_poll'><b>Persistent Storage polling rate</b></label>
                        <input type='text' id='pstorage_thread_poll' name='pstorage_thread_poll' value='10'>"""
                    else:
                        return_str += """
                            <input id="pstorage_thread" type="checkbox" checked>
                            <span class="checkmark"></span>
                        </label>
                        <label for='pstorage_thread_poll'><b>Persistent Storage polling rate</b></label>
                        <input type='text' id='pstorage_thread_poll' name='pstorage_thread_poll' value='""" + pstorage_poll + "'>"
                    
                    return_str += """
                        <br>
                        <br>
                        <br>
                        <label class="container">
                            <b>Start OpenPLC in RUN mode</b>"""
                            
                    if (start_run == 'false'):
                        return_str += """
                            <input id="auto_run" type="checkbox">
                            <span class="checkmark"></span>
                        </label>
                        <input type='hidden' value='false' id='auto_run_text' name='auto_run_text'/>"""
                    else:
                        return_str += """
                            <input id="auto_run" type="checkbox" checked>
                            <span class="checkmark"></span>
                        </label>
                        <input type='hidden' value='true' id='auto_run_text' name='auto_run_text'/>"""
                    
                    return_str += """
                        <br>
                        <h2>Slave Devices</h2>
                        <label for='slave_polling_period'><b>Polling Period (ms)</b></label>
                        <input type='text' id='slave_polling_period' name='slave_polling_period' value='""" + slave_polling + "'>"
                    
                    return_str += """
                        <br>
                        <br>
                        <br>
                        <label for='slave_timeout'><b>Timeout (ms)</b></label>
                        <input type='text' id='slave_timeout' name='slave_timeout' value='""" + slave_timeout + "'>"
                    
                    return_str += pages.settings_tail
                    
                except Error as e:
                    return_str += "error connecting to the database" + str(e)
            else:
                return_str += "Error opening DB"

            return return_str

        elif (flask.request.method == 'POST'):
            modbus_port = flask.request.form.get('modbus_server_port')
            dnp3_port = flask.request.form.get('dnp3_server_port')
            enip_port = flask.request.form.get('enip_server_port')
            pstorage_poll = flask.request.form.get('pstorage_thread_poll')
            start_run = flask.request.form.get('auto_run_text')
            slave_polling = flask.request.form.get('slave_polling_period')
            slave_timeout = flask.request.form.get('slave_timeout')
            
            database = "../etc/openplc.db"
            conn = create_connection(database)
            if (conn != None):
                try:
                    cur = conn.cursor()
                    if (modbus_port == None):
                        cur.execute("UPDATE Settings SET Value = 'disabled' WHERE Key = 'Modbus_port'")
                        conn.commit()
                    else:
                        cur.execute("UPDATE Settings SET Value = ? WHERE Key = 'Modbus_port'", (str(modbus_port),))
                        conn.commit()
                        
                    if (dnp3_port == None):
                        cur.execute("UPDATE Settings SET Value = 'disabled' WHERE Key = 'Dnp3_port'")
                        conn.commit()
                    else:
                        cur.execute("UPDATE Settings SET Value = ? WHERE Key = 'Dnp3_port'", (str(dnp3_port),))
                        conn.commit()
                        
                    if (enip_port == None):
                        cur.execute("UPDATE Settings SET Value = 'disabled' WHERE Key = 'Enip_port'")
                        conn.commit()
                    else:
                        cur.execute("UPDATE Settings SET Value = ? WHERE Key = 'Enip_port'", (str(enip_port),))
                        conn.commit()
                        
                    if (pstorage_poll == None):
                        cur.execute("UPDATE Settings SET Value = 'disabled' WHERE Key = 'Pstorage_polling'")
                        conn.commit()
                    else:
                        cur.execute("UPDATE Settings SET Value = ? WHERE Key = 'Pstorage_polling'", (str(pstorage_poll),))
                        conn.commit()
                        
                    if (start_run == 'true'):
                        cur.execute("UPDATE Settings SET Value = 'true' WHERE Key = 'Start_run_mode'")
                        conn.commit()
                    else:
                        cur.execute("UPDATE Settings SET Value = 'false' WHERE Key = 'Start_run_mode'")
                        conn.commit()
                        
                    cur.execute("UPDATE Settings SET Value = ? WHERE Key = 'Slave_polling'", (str(slave_polling),))
                    conn.commit()
                    
                    cur.execute("UPDATE Settings SET Value = ? WHERE Key = 'Slave_timeout'", (str(slave_timeout),))
                    conn.commit()
                    
                    cur.close()
                    conn.close()
                    configure_runtime()
                    generate_mbconfig()
                    return flask.redirect(flask.url_for('dashboard'))
                    
                except Error as e:
                    print("error connecting to the database" + str(e))
                    return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.<br><br>Error: ' + str(e)
            else:
                return 'Error connecting to the database. Make sure that your ../etc/openplc.db file is not corrupt.'
        

@app.route('/logout')
def logout():
    if (flask_login.current_user.is_authenticated == False):
        return flask.redirect(flask.url_for('login'))
    else:
        monitor.stop_monitor()
        flask_login.logout_user()
        return flask.redirect(flask.url_for('login'))


@login_manager.unauthorized_handler
def unauthorized_handler():
    return 'Unauthorized'
    
#----------------------------------------------------------------------------
#Creates a connection with the SQLite database.
#----------------------------------------------------------------------------
""" Create a connection to the database file """
def create_connection(db_file):
   try:
      conn = sqlite3.connect(db_file)
      return conn
   except Error as e:
      print(e)

   return None

#----------------------------------------------------------------------------
#Main dummy function. Only displays a message and exits. The app keeps
#running on the background by Flask
#----------------------------------------------------------------------------
def start_server(address="127.0.0.1", port=8080,
                 database=DB_FILE,
                 debug=False):
    print("Starting the web interface...")

    DB_FILE = database
    if not os.path.exists(DB_FILE):
        s = "The database file `%s` does not exist\n" % DB_FILE
        print(s)
        return


    #Load information about current program on the openplc_runtime object
    program_dir = os.path.abspath(os.path.join(ETC_PATH, 'active_program'))
    file = open(program_dir, "r")
    st_file = file.read()
    st_file = st_file.replace('\r','').replace('\n','')
    

    #sys.setdefaultencoding('UTF8')
    
    # database = "../etc/openplc.db"
    # conn = create_connection(database)
    # if (conn != None):
    #     try:
    #         cur = conn.cursor()
    #         cur.execute("SELECT * FROM Programs WHERE File=?", (st_file,))
    #         #cur.execute("SELECT * FROM Programs")
    #         row = cur.fetchone()
    #         openplc_runtime.project_name = str(row[1])
    #         openplc_runtime.project_description = str(row[2])
    #         openplc_runtime.project_file = str(row[3])
    #
    #         cur.execute("SELECT * FROM Settings")
    #         rows = cur.fetchall()
    #         cur.close()
    #         conn.close()
    #
    #         for row in rows:
    #             if (row[0] == "Start_run_mode"):
    #                 start_run = str(row[1])
    #
    #         if (start_run == 'true'):
    #             print("Initializing OpenPLC in RUN mode...")
    #             openplc_runtime.start_runtime()
    #             time.sleep(1)
    #             configure_runtime()
    #
    #         app.run(debug=False, host='0.0.0.0', threaded=True, port=8080)
    #
    #     except Error as e:
    #         print("error connecting to the database" + str(e))
    # else:
    #     print("error connecting to the database")

    #socketio.run(app, host=args.address, port=args.port, debug=True)
    app.run(debug=debug, host=address, threaded=False, port=port)