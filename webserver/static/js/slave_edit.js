
var dev_protocol = document.getElementById('dev_protocol');
var tcpdiv = document.getElementById("tcp-stuff");
var rtudiv = document.getElementById("rtu-stuff");

var devport = document.getElementById("dev_port");
var devid = document.getElementById("dev_id");

var devbaud = document.getElementById("dev_baud");
var devparity = document.getElementById("dev_parity");
var devdata = document.getElementById("dev_data");
var devstop = document.getElementById("dev_stop");

var distart = document.getElementById("di_start");
var disize = document.getElementById("di_size");
var dostart = document.getElementById("do_start");
var dosize = document.getElementById("do_size");
var aistart = document.getElementById("ai_start");
var aisize = document.getElementById("ai_size");
var aorstart = document.getElementById("aor_start");
var aorsize = document.getElementById("aor_size");
var aowstart = document.getElementById("aow_start");
var aowsize = document.getElementById("aow_size");

window.onload = function()
{
    setupPageContent()
    //LoadValuesFromDB()
}

function turnElementOn(element)
{
    element.readOnly = false
    element.value = ""
    //element.style.backgroundColor = "white"
    //element.style.color = "black"
}

function turnElementOff(element)
{
    element.readOnly = true
   // element.style.backgroundColor = "#F8F8F8"
    //element.style.color = "#9C9C9C"
}

dev_protocol.onchange = function()
{
    first_time_edit = false;
    setupPageContent()
}

function setupPageContent()
{
    var dtype = dev_protocol.options[dev_protocol.selectedIndex].value;


    switch(dtype){

    case "TCP":
        tcpdiv.style.display = "block";
        rtudiv.style.display = "none";

        turnElementOn(devport);
        turnElementOn(devid);
        turnElementOn(distart);
        turnElementOn(disize);
        turnElementOn(dostart);
        turnElementOn(dosize);
        turnElementOn(aistart);
        turnElementOn(aisize);
        turnElementOn(aorstart);
        turnElementOn(aorsize);
        turnElementOn(aowstart);
        turnElementOn(aowsize);
        break;

    case "ESP32":

        tcpdiv.style.display = "block";
        rtudiv.style.display = "none";

        turnElementOff(devport);
        devport.value = "502";
        turnElementOff(devid);
        devid.value = "0";
        turnElementOff(distart);
        distart.value = "0";
        turnElementOff(disize);
        disize.value = "8";
        turnElementOff(dostart);
        dostart.value = "0";
        turnElementOff(dosize);
        dosize.value = "8";
        turnElementOff(aistart);
        aistart.value = "0";
        turnElementOff(aisize);
        aisize.value = "1";
        turnElementOff(aorstart);
        aorstart.value = "0";
        turnElementOff(aorsize);
        aorsize.value = "0";
        turnElementOff(aowstart);
        aowstart.value = "0";
        turnElementOff(aowsize);
        aowsize.value = "1";
        break;

    case "ESP8266":

            tcpdiv.style.display = "block";
            rtudiv.style.display = "none";

            turnElementOff(devport);
            devport.value = "502"
            turnElementOff(devid)
            devid.value = "0"
            turnElementOff(distart)
            distart.value = "0"
            turnElementOff(disize)
            disize.value = "8"
            turnElementOff(dostart)
            dostart.value = "0"
            turnElementOff(dosize)
            dosize.value = "8"
            turnElementOff(aistart)
            aistart.value = "0"
            turnElementOff(aisize)
            aisize.value = "1"
            turnElementOff(aorstart)
            aorstart.value = "0"
            turnElementOff(aorsize)
            aorsize.value = "0"
            turnElementOff(aowstart)
            aowstart.value = "0"
            turnElementOff(aowsize)
            aowsize.value = "1"

    case "RTU":

            tcpdiv.style.display = "none"
            rtudiv.style.display = "block"

            turnElementOn(devid)
            turnElementOn(devbaud)
            turnElementOn(devparity)
            devparity.value = "None"
            turnElementOn(devdata)
            turnElementOn(devstop)
            turnElementOn(distart)
            turnElementOn(disize)
            turnElementOn(dostart)
            turnElementOn(dosize)
            turnElementOn(aistart)
            turnElementOn(aisize)
            turnElementOn(aorstart)
            turnElementOn(aorsize)
            turnElementOn(aowstart)
            turnElementOn(aowsize)

    case "Uno":

            tcpdiv.style.display = "none"
            rtudiv.style.display = "block"

            turnElementOff(devid)
            devid.value = "0"
            turnElementOff(devbaud)
            devbaud.value = "115200"
            turnElementOff(devparity)
            devparity.value = "None"
            turnElementOff(devdata)
            devdata.value = "8"
            turnElementOff(devstop)
            devstop.value = "1"
            turnElementOff(distart)
            distart.value = "0"
            turnElementOff(disize)
            disize.value = "5"
            turnElementOff(dostart)
            dostart.value = "0"
            turnElementOff(dosize)
            dosize.value = "4"
            turnElementOff(aistart)
            aistart.value = "0"
            turnElementOff(aisize)
            aisize.value = "6"
            turnElementOff(aorstart)
            aorstart.value = "0"
            turnElementOff(aorsize)
            aorsize.value = "0"
            turnElementOff(aowstart)
            aowstart.value = "0"
            turnElementOff(aowsize)
            aowsize.value = "3"
            break;

    case "Mega":

            tcpdiv.style.display = "none"
            rtudiv.style.display = "block"

            turnElementOff(devid)
            devid.value = "0"
            turnElementOff(devbaud)
            devbaud.value = "115200"
            turnElementOff(devparity)
            devparity.value = "None"
            turnElementOff(devdata)
            devdata.value = "8"
            turnElementOff(devstop)
            devstop.value = "1"
            turnElementOff(distart)
            distart.value = "0"
            turnElementOff(disize)
            disize.value = "24"
            turnElementOff(dostart)
            dostart.value = "0"
            turnElementOff(dosize)
            dosize.value = "16"
            turnElementOff(aistart)
            aistart.value = "0"
            turnElementOff(aisize)
            aisize.value = "16"
            turnElementOff(aorstart)
            aorstart.value = "0"
            turnElementOff(aorsize)
            aorsize.value = "0"
            turnElementOff(aowstart)
            aowstart.value = "0"
            turnElementOff(aowsize)
            aowsize.value = "12"
            break;
    }


}



function validateForm()
{
    var devname = document.forms["uploadForm"]["dev_name"].value;
    var devid = document.forms["uploadForm"]["dev_id"].value;

    var devip = document.forms["uploadForm"]["dev_ip"].value;
    var devport = document.forms["uploadForm"]["dev_port"].value;

    var devbaud = document.forms["uploadForm"]["dev_baud"].value;
    var devdata = document.forms["uploadForm"]["dev_data"].value;
    var devstop = document.forms["uploadForm"]["dev_stop"].value;

    var distart = document.forms["uploadForm"]["di_start"].value;
    var disize = document.forms["uploadForm"]["di_size"].value;
    var dostart = document.forms["uploadForm"]["do_start"].value;
    var dosize = document.forms["uploadForm"]["do_size"].value;
    var aistart = document.forms["uploadForm"]["ai_start"].value;
    var aisize = document.forms["uploadForm"]["ai_size"].value;
    var aorstart = document.forms["uploadForm"]["aor_start"].value;
    var aorsize = document.forms["uploadForm"]["aor_size"].value;
    var aowstart = document.forms["uploadForm"]["aow_start"].value;
    var aowstart = document.forms["uploadForm"]["aow_start"].value;
    var aowsize = document.forms["uploadForm"]["aow_size"].value;


    if (devname == "" || devid == "" || distart == "" || disize == "" || dostart == "" || dosize == "" || aistart == "" || aisize == "" || aorstart == "" || aorsize == "" || aowstart == "" || aowsize == "")
    {
        alert("Please fill out all the fields before saving!");
        return false;
    }

    var device_type = dev_protocol.options[dev_protocol.selectedIndex].value
    if (device_type=="TCP" || device_type=="ESP32" || device_type=="ESP8266")
    {
        if (devip == "" || devport == "")
        {
            alert("Please fill out all the fields before saving!");
            return false;
        }
    }
    else
    {
        if (devbaud == "" || devdata == "" || devstop == "")
        {
            alert("Please fill out all the fields before saving!");
            return false;
        }
    }
    alert("ok");
    return false;
    return true;
}