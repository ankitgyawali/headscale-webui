# pylint: disable=line-too-long, wrong-import-order

import headscale, helper, pytz, os, yaml, logging
from flask              import Flask, Markup, render_template
from datetime           import datetime
from dateutil           import parser
from concurrent.futures import ALL_COMPLETED, wait
from flask_executor     import Executor

LOG_LEVEL = os.environ["LOG_LEVEL"].replace('"', '').upper()
# Initiate the Flask application and logging:
app = Flask(__name__, static_url_path="/static")
match LOG_LEVEL:
    case "DEBUG"   : app.logger.setLevel(logging.DEBUG)
    case "INFO"    : app.logger.setLevel(logging.INFO)
    case "WARNING" : app.logger.setLevel(logging.WARNING)
    case "ERROR"   : app.logger.setLevel(logging.ERROR)
    case "CRITICAL": app.logger.setLevel(logging.CRITICAL)
executor = Executor(app)

def render_overview():
    app.logger.info("Rendering the Overview page")
    url           = headscale.get_url()
    api_key       = headscale.get_api_key()

    timezone         = pytz.timezone(os.environ["TZ"] if os.environ["TZ"] else "UTC")
    local_time       = timezone.localize(datetime.now())
    
    # Overview page will just read static information from the config file and display it
    # Open the config.yaml and parse it.
    config_file = ""
    try:    
        config_file = open("/etc/headscale/config.yml",  "r")
        app.logger.info("Opening /etc/headscale/config.yml")
    except: 
        config_file = open("/etc/headscale/config.yaml", "r")
        app.logger.info("Opening /etc/headscale/config.yaml")
    config_yaml = yaml.safe_load(config_file)

    # Get and display the following information:
    # Overview of the server's machines, users, preauth keys, API key expiration, server version
    
    # Get all machines:
    machines = headscale.get_machines(url, api_key)
    machines_count = len(machines["machines"])

    # Need to check if routes are attached to an active machine:
    # ISSUE:  https://github.com/iFargle/headscale-webui/issues/36 
    # ISSUE:  https://github.com/juanfont/headscale/issues/1228 

    # Get all routes:
    routes = headscale.get_routes(url,api_key)

    total_routes = 0
    for route in routes["routes"]:
        if int(route['machine']['id']) != 0: 
            total_routes += 1

    enabled_routes = 0
    for route in routes["routes"]:
        if route["enabled"] and route['advertised'] and int(route['machine']['id']) != 0: 
            enabled_routes += 1

    # Get a count of all enabled exit routes
    exits_count = 0
    exits_enabled_count = 0
    for route in routes["routes"]:
        if route['advertised'] and int(route['machine']['id']) != 0:
            if route["prefix"] == "0.0.0.0/0" or route["prefix"] == "::/0":
                exits_count +=1
                if route["enabled"]:
                    exits_enabled_count += 1

    # Get User and PreAuth Key counts
    user_count        = 0
    usable_keys_count = 0
    users = headscale.get_users(url, api_key)
    for user in users["users"]:
        user_count +=1
        preauth_keys = headscale.get_preauth_keys(url, api_key, user["name"])
        for key in preauth_keys["preAuthKeys"]:
            expiration_parse = parser.parse(key["expiration"])
            key_expired = True if expiration_parse < local_time else False
            if key["reusable"] and not key_expired: usable_keys_count += 1
            if not key["reusable"] and not key["used"] and not key_expired: usable_keys_count += 1

    # General Content variables:
    ip_prefixes, server_url, disable_check_updates, ephemeral_node_inactivity_timeout, node_update_check_interval = "N/A", "N/A", "N/A", "N/A", "N/A"
    if "ip_prefixes"                       in config_yaml:  ip_prefixes                       = str(config_yaml["ip_prefixes"])
    if "server_url"                        in config_yaml:  server_url                        = str(config_yaml["server_url"])
    if "disable_check_updates"             in config_yaml:  disable_check_updates             = str(config_yaml["disable_check_updates"])
    if "ephemeral_node_inactivity_timeout" in config_yaml:  ephemeral_node_inactivity_timeout = str(config_yaml["ephemeral_node_inactivity_timeout"])
    if "node_update_check_interval"        in config_yaml:  node_update_check_interval        = str(config_yaml["node_update_check_interval"])

    # OIDC Content variables:
    issuer, client_id, scope, use_expiry_from_token, expiry = "N/A", "N/A", "N/A", "N/A", "N/A"
    if "oidc" in config_yaml:
        if "issuer"                in config_yaml["oidc"] : issuer                = str(config_yaml["oidc"]["issuer"])                
        if "client_id"             in config_yaml["oidc"] : client_id             = str(config_yaml["oidc"]["client_id"])             
        if "scope"                 in config_yaml["oidc"] : scope                 = str(config_yaml["oidc"]["scope"])                 
        if "use_expiry_from_token" in config_yaml["oidc"] : use_expiry_from_token = str(config_yaml["oidc"]["use_expiry_from_token"]) 
        if "expiry"                in config_yaml["oidc"] : expiry                = str(config_yaml["oidc"]["expiry"])   

    # Embedded DERP server information.
    enabled, region_id, region_code, region_name, stun_listen_addr = "N/A", "N/A", "N/A", "N/A", "N/A"
    if "derp" in config_yaml:
        if "server" in config_yaml["derp"] and config_yaml["derp"]["server"]["enabled"]:
            if "enabled"          in config_yaml["derp"]["server"]: enabled          = str(config_yaml["derp"]["server"]["enabled"])          
            if "region_id"        in config_yaml["derp"]["server"]: region_id        = str(config_yaml["derp"]["server"]["region_id"])        
            if "region_code"      in config_yaml["derp"]["server"]: region_code      = str(config_yaml["derp"]["server"]["region_code"])      
            if "region_name"      in config_yaml["derp"]["server"]: region_name      = str(config_yaml["derp"]["server"]["region_name"])      
            if "stun_listen_addr" in config_yaml["derp"]["server"]: stun_listen_addr = str(config_yaml["derp"]["server"]["stun_listen_addr"]) 
    
    nameservers, magic_dns, domains, base_domain = "N/A", "N/A", "N/A", "N/A"
    if "dns_config" in config_yaml:
        if "nameservers" in config_yaml["dns_config"]: nameservers = str(config_yaml["dns_config"]["nameservers"]) 
        if "magic_dns"   in config_yaml["dns_config"]: magic_dns   = str(config_yaml["dns_config"]["magic_dns"])   
        if "domains"     in config_yaml["dns_config"]: domains     = str(config_yaml["dns_config"]["domains"])     
        if "base_domain" in config_yaml["dns_config"]: base_domain = str(config_yaml["dns_config"]["base_domain"]) 

    # Start putting the content together
    overview_content = """
    <div class="row">
        <div class="col s1"></div>
        <div class="col s10">
            <ul class="collection with-header z-depth-1">
                <li class="collection-header"><h4>Server Statistics</h4></li>
                <li class="collection-item"><div>Machines Added       <div class="secondary-content overview-page">"""+ str(machines_count)                               +"""</div></div></li>
                <li class="collection-item"><div>Users Added          <div class="secondary-content overview-page">"""+ str(user_count)                                   +"""</div></div></li>
                <li class="collection-item"><div>Usable Preauth Keys  <div class="secondary-content overview-page">"""+ str(usable_keys_count)                            +"""</div></div></li>
                <li class="collection-item"><div>Enabled/Total Routes <div class="secondary-content overview-page">"""+ str(enabled_routes) +"""/"""+str(total_routes)    +"""</div></div></li>
                <li class="collection-item"><div>Enabled/Total Exits  <div class="secondary-content overview-page">"""+ str(exits_enabled_count) +"""/"""+str(exits_count)+"""</div></div></li>
            </ul>
        </div>
        <div class="col s1"></div>
    </div>
    """
    general_content = """
    <div class="row">
        <div class="col s1"></div>
        <div class="col s10">
            <ul class="collection with-header z-depth-1">
                <li class="collection-header"><h4>General</h4></li>
                <li class="collection-item"><div>IP Prefixes                       <div class="secondary-content overview-page">"""+ ip_prefixes                       +"""</div></div></li>
                <li class="collection-item"><div>Server URL                        <div class="secondary-content overview-page">"""+ server_url                        +"""</div></div></li>
                <li class="collection-item"><div>Updates Disabled                  <div class="secondary-content overview-page">"""+ disable_check_updates             +"""</div></div></li>
                <li class="collection-item"><div>Ephemeral Node Inactivity Timeout <div class="secondary-content overview-page">"""+ ephemeral_node_inactivity_timeout +"""</div></div></li>
                <li class="collection-item"><div>Node Update Check Interval        <div class="secondary-content overview-page">"""+ node_update_check_interval        +"""</div></div></li>
            </ul>
        </div>
        <div class="col s1"></div>
    </div>
    """
    oidc_content = """
    <div class="row">
        <div class="col s1"></div>
        <div class="col s10">
            <ul class="collection with-header z-depth-1">
                <li class="collection-header"><h4>Headscale OIDC</h4></li>
                <li class="collection-item"><div>Issuer                <div class="secondary-content overview-page">"""+ issuer                +"""</div></div></li>
                <li class="collection-item"><div>Client ID             <div class="secondary-content overview-page">"""+ client_id             +"""</div></div></li>
                <li class="collection-item"><div>Scope                 <div class="secondary-content overview-page">"""+ scope                 +"""</div></div></li>
                <li class="collection-item"><div>Use OIDC Token Expiry <div class="secondary-content overview-page">"""+ use_expiry_from_token +"""</div></div></li>
                <li class="collection-item"><div>Expiry                <div class="secondary-content overview-page">"""+ expiry                +"""</div></div></li>
            </ul>
        </div>
        <div class="col s1"></div>
    </div>
    """
    derp_content = """
    <div class="row">
        <div class="col s1"></div>
        <div class="col s10">
            <ul class="collection with-header z-depth-1">
                <li class="collection-header"><h4>Embedded DERP</h4></li>
                <li class="collection-item"><div>Enabled     <div class="secondary-content overview-page">"""+ enabled          +"""</div></div></li>
                <li class="collection-item"><div>Region ID   <div class="secondary-content overview-page">"""+ region_id        +"""</div></div></li>
                <li class="collection-item"><div>Region Code <div class="secondary-content overview-page">"""+ region_code      +"""</div></div></li>
                <li class="collection-item"><div>Region Name <div class="secondary-content overview-page">"""+ region_name      +"""</div></div></li>
                <li class="collection-item"><div>STUN Address<div class="secondary-content overview-page">"""+ stun_listen_addr +"""</div></div></li>
            </ul>
        </div>
        <div class="col s1"></div>
    </div>
    """
    dns_content = """
    <div class="row">
        <div class="col s1"></div>
        <div class="col s10">
            <ul class="collection with-header z-depth-1">
                <li class="collection-header"><h4>DNS</h4></li>
                <li class="collection-item"><div>DNS Nameservers <div class="secondary-content overview-page">"""+  nameservers  +"""</div></div></li>
                <li class="collection-item"><div>MagicDNS        <div class="secondary-content overview-page">"""+  magic_dns    +"""</div></div></li>
                <li class="collection-item"><div>Search Domains  <div class="secondary-content overview-page">"""+  domains      +"""</div></div></li>
                <li class="collection-item"><div>Base Domain     <div class="secondary-content overview-page">"""+  base_domain  +"""</div></div></li>
            </ul>
        </div>
        <div class="col s1"></div>
    </div>
    """

    # Remove content that isn't needed:
    # Remove OIDC if it isn't available:
    if "oidc" not in config_yaml: oidc_content = ""
    # Remove DERP if it isn't available or isn't enabled
    if "derp" not in config_yaml: 
        derp_content = ""
    if "derp" in config_yaml:
        if "server" in config_yaml["derp"]:
            if str(config_yaml["derp"]["server"]["enabled"]) == "False":
                derp_content = ""

    # TODO:  
    #     Whether there are custom DERP servers
    #         If there are custom DERP servers, get the file location from the config file.  Assume mapping is the same.
    #     Whether the built-in DERP server is enabled 
    #     The IP prefixes
    #     The DNS config

    if config_yaml["derp"]["paths"]: pass
    #   # open the path:
    #   derp_file = 
    #   config_file = open("/etc/headscale/config.yaml", "r")
    #   config_yaml = yaml.safe_load(config_file)
    #     The ACME config, if not empty
    #     Whether updates are running
    #     Whether metrics are enabled (and their listen addr)
    #     The log level
    #     What kind of Database is being used to drive headscale

    content = "<br>" + overview_content + general_content + derp_content + oidc_content + dns_content + ""
    return Markup(content)

def thread_machine_content(machine, machine_content, idx):
    # machine      = passed in machine information
    # content      = place to write the content

    app.logger.debug("Machine Information")
    app.logger.debug(str(machine))

    url           = headscale.get_url()
    api_key       = headscale.get_api_key()

    # Set the current timezone and local time
    timezone   = pytz.timezone(os.environ["TZ"] if os.environ["TZ"] else "UTC")
    local_time = timezone.localize(datetime.now())

    # Get the machines routes
    pulled_routes = headscale.get_machine_routes(url, api_key, machine["id"])
    routes = ""

    # Test if the machine is an exit node:
    exit_node = False
    # If the LENGTH of "routes" is NULL/0, there are no routes, enabled or disabled:
    if len(pulled_routes["routes"]) > 0:
        advertised_and_enabled = False
        advertised_route = False
        # First, check if there are any routes that are both enabled and advertised
        for route in pulled_routes["routes"]:
            if route ["advertised"] and route["enabled"]: 
                advertised_and_enabled = True
            if route["advertised"]:
                advertised_route = True
        if advertised_and_enabled or advertised_route:
            routes = """
                <li class="collection-item avatar">
                    <i class="material-icons circle">directions</i>
                    <span class="title">Routes</span>
                    <p><div>
            """
            for route in pulled_routes["routes"]:
                app.logger.debug("Route:  ["+str(route['machine']['name'])+"] id: "+str(route['id'])+" / prefix: "+str(route['prefix'])+" enabled?:  "+str(route['enabled']))
                # Check if the route is enabled:
                route_enabled = "red"
                route_tooltip = 'enable'
                if route["enabled"]:
                    route_enabled = "green"
                    route_tooltip = 'disable'
                    if route["prefix"] == "0.0.0.0/0" or route["prefix"] == "::/0" and str(route["enabled"]) == "True":
                        exit_node = True
                routes = routes+"""
                <p 
                    class='waves-effect waves-light btn-small """+route_enabled+""" lighten-2 tooltipped'
                    data-position='top' data-tooltip='Click to """+route_tooltip+"""'
                    id='"""+route['id']+"""'
                    onclick="toggle_route("""+route['id']+""", '"""+str(route['enabled'])+"""')">
                    """+route['prefix']+"""
                </p>
                """
            routes = routes+"</div></p></li>"

    # Get machine tags
    tag_array = ""
    for tag in machine["forcedTags"]: tag_array = tag_array+"{tag: '"+tag[4:]+"'}, "
    tags = """
        <li class="collection-item avatar">
            <i class="material-icons circle tooltipped" data-position="right" data-tooltip="Spaces will be replaced with a dash (-) upon page refresh">label</i>
            <span class="title">Tags</span>
            <p><div style='margin: 0px' class='chips' id='"""+machine["id"]+"""-tags'></div></p>
        </li>
        <script>
            window.addEventListener('load', 
                function() { 
                    var instances = M.Chips.init ( 
                        document.getElementById('"""+machine['id']+"""-tags'),  ({
                            data:["""+tag_array+"""], 
                            onChipDelete() { delete_chip("""+machine["id"]+""", this.chipsData) }, 
                            onChipAdd()    { add_chip("""+machine["id"]+""",    this.chipsData) }
                        }) 
                    );
                }, false
            )
        </script>
        """

    # Get the machine IP's
    machine_ips = "<ul>"
    for ip_address in machine["ipAddresses"]:
        machine_ips = machine_ips+"<li>"+ip_address+"</li>"
    machine_ips = machine_ips+"</ul>"

    # Format the dates for easy readability
    last_seen_parse   = parser.parse(machine["lastSeen"])
    last_seen_local   = last_seen_parse.astimezone(timezone)
    last_seen_delta   = local_time - last_seen_local
    last_seen_print   = helper.pretty_print_duration(last_seen_delta)
    last_seen_time    = str(last_seen_local.strftime('%A %m/%d/%Y, %H:%M:%S'))+" "+str(timezone)+" ("+str(last_seen_print)+")"
    
    last_update_parse = local_time if machine["lastSuccessfulUpdate"] is None else parser.parse(machine["lastSuccessfulUpdate"])
    last_update_local = last_update_parse.astimezone(timezone)
    last_update_delta = local_time - last_update_local
    last_update_print = helper.pretty_print_duration(last_update_delta)
    last_update_time  = str(last_update_local.strftime('%A %m/%d/%Y, %H:%M:%S'))+" "+str(timezone)+" ("+str(last_update_print)+")"

    created_parse     = parser.parse(machine["createdAt"])
    created_local     = created_parse.astimezone(timezone)
    created_delta     = local_time - created_local
    created_print     = helper.pretty_print_duration(created_delta)
    created_time      = str(created_local.strftime('%A %m/%d/%Y, %H:%M:%S'))+" "+str(timezone)+" ("+str(created_print)+")"

    # If there is no expiration date, we don't need to do any calculations:
    if machine["expiry"] != "0001-01-01T00:00:00Z":
        expiry_parse     = parser.parse(machine["expiry"])
        expiry_local     = expiry_parse.astimezone(timezone)
        expiry_delta     = expiry_local - local_time
        expiry_print     = helper.pretty_print_duration(expiry_delta, "expiry")
        if str(expiry_local.strftime('%Y')) in ("0001",  "9999", "0000"):
            expiry_time  = "No expiration date."
        elif int(expiry_local.strftime('%Y')) > int(expiry_local.strftime('%Y'))+2:
            expiry_time  = str(expiry_local.strftime('%m/%Y'))+" "+str(timezone)+" ("+str(expiry_print)+")"
        else: 
            expiry_time  = str(expiry_local.strftime('%A %m/%d/%Y, %H:%M:%S'))+" "+str(timezone)+" ("+str(expiry_print)+")"

        expiring_soon = True if int(expiry_delta.days) < 14 and int(expiry_delta.days) > 0 else False
        app.logger.debug("Machine:  "+machine["name"]+" expires:  "+str(expiry_local.strftime('%Y'))+" / "+str(expiry_delta.days))
    else:
        expiry_time  = "No expiration date."
        expiring_soon = False
        app.logger.debug("Machine:  "+machine["name"]+" has no expiration date")


    # Get the first 10 characters of the PreAuth Key:
    if machine["preAuthKey"]:
        preauth_key = str(machine["preAuthKey"]["key"])[0:10]
    else: preauth_key = "None"

    # Set the status badge color:
    text_color = helper.text_color_duration(last_seen_delta)
    # Set the user badge color:
    user_color = helper.get_color(int(machine["user"]["id"]))

    # Generate the various badges:
    status_badge      = "<i class='material-icons left tooltipped "+text_color+"' data-position='top' data-tooltip='Last Seen:  "+last_seen_print+"' id='"+machine["id"]+"-status'>fiber_manual_record</i>"
    user_badge        = "<span class='badge ipinfo " + user_color + " white-text hide-on-small-only' id='"+machine["id"]+"-ns-badge'>"+machine["user"]["name"]+"</span>"
    exit_node_badge   = "" if not exit_node else "<span class='badge grey white-text text-lighten-4 tooltipped' data-position='left' data-tooltip='This machine has an enabled exit route.'>Exit Node</span>"
    expiration_badge  = "" if not expiring_soon else "<span class='badge red white-text text-lighten-4 tooltipped' data-position='left' data-tooltip='This machine expires soon.'>Expiring!</span>"

    machine_content[idx] = (str(render_template(
        'machines_card.html', 
        given_name        = machine["givenName"],
        machine_id        = machine["id"],
        hostname          = machine["name"],
        ns_name           = machine["user"]["name"],
        ns_id             = machine["user"]["id"],
        ns_created        = machine["user"]["createdAt"],
        last_seen         = str(last_seen_print),
        last_update       = str(last_update_print),
        machine_ips       = Markup(machine_ips),
        advertised_routes = Markup(routes),
        exit_node_badge   = Markup(exit_node_badge),
        status_badge      = Markup(status_badge),
        user_badge        = Markup(user_badge),
        last_update_time  = str(last_update_time),
        last_seen_time    = str(last_seen_time),
        created_time      = str(created_time),
        expiry_time       = str(expiry_time),
        preauth_key       = str(preauth_key),
        expiration_badge  = Markup(expiration_badge),
        machine_tags      = Markup(tags),
    )))
    app.logger.info("Finished thread for machine "+machine["givenName"]+" index "+str(idx))

# Render the cards for the machines page:
def render_machines_cards():
    app.logger.info("Rendering machine cards")
    url           = headscale.get_url()
    api_key       = headscale.get_api_key()
    machines_list = headscale.get_machines(url, api_key)

    #########################################
    # Thread this entire thing.  
    num_threads = len(machines_list["machines"])
    iterable = []
    machine_content = {}
    for i in range (0, num_threads):
        app.logger.debug("Appending iterable:  "+str(i))
        iterable.append(i)
    # Flask-Executor Method:
    if LOG_LEVEL == "DEBUG":
        # DEBUG:  Do in a forloop:
        for idx in iterable: thread_machine_content(machines_list["machines"][idx], machine_content, idx)
    else:
        app.logger.info("Starting futures")
        futures = [executor.submit(thread_machine_content, machines_list["machines"][idx], machine_content, idx) for idx in iterable]
        # Wait for the executor to finish all jobs:
        wait(futures, return_when=ALL_COMPLETED)
        app.logger.info("Finished futures")

    # Sort the content by machine_id:
    sorted_machines = {key: val for key, val in sorted(machine_content.items(), key = lambda ele: ele[0])}

    content = "<div class='u-flex u-justify-space-evenly u-flex-wrap u-gap-1'>"
    # Print the content

    for index in range(0, num_threads):
        content = content+str(sorted_machines[index])

    content = content+"</div>"

    return Markup(content)

# Render the cards for the Users page:
def render_users_cards():
    app.logger.info("Rendering Users cards")
    url       = headscale.get_url()
    api_key   = headscale.get_api_key()
    user_list = headscale.get_users(url, api_key)

    content = "<div class='u-flex u-justify-space-evenly u-flex-wrap u-gap-1'>"
    for user in user_list["users"]:
        # Get all preAuth Keys in the user, only display if one exists:
        preauth_keys_collection = build_preauth_key_table(user["name"])

        # Set the user badge color:
        user_color = helper.get_color(int(user["id"]), "text")

        # Generate the various badges:
        status_badge      = "<i class='material-icons left "+user_color+"' id='"+user["id"]+"-status'>fiber_manual_record</i>"

        content = content + render_template(
            'users_card.html', 
            status_badge            = Markup(status_badge),
            user_name               = user["name"],
            user_id                 = user["id"],
            preauth_keys_collection = Markup(preauth_keys_collection)
        ) 
    content = content+"</div>"
    return Markup(content)

# Builds the preauth key table for the User page
def build_preauth_key_table(user_name):
    app.logger.info("Building the PreAuth key table for User:  %s", str(user_name))
    url            = headscale.get_url()
    api_key        = headscale.get_api_key()

    preauth_keys = headscale.get_preauth_keys(url, api_key, user_name)
    preauth_keys_collection = """<li class="collection-item avatar">
            <span
                class='badge grey lighten-2 btn-small' 
                onclick='toggle_expired()'
            >Toggle Expired</span>
            <span 
                href="#card_modal" 
                class='badge grey lighten-2 btn-small modal-trigger' 
                onclick="load_modal_add_preauth_key('"""+user_name+"""')"
            >Add PreAuth Key</span>
            <i class="material-icons circle">vpn_key</i>
            <span class="title">PreAuth Keys</span>
            """
    if len(preauth_keys["preAuthKeys"]) == 0: preauth_keys_collection += "<p>No keys defined for this user</p>"
    if len(preauth_keys["preAuthKeys"]) > 0:
        preauth_keys_collection += """
                <table class="responsive-table striped" id='"""+user_name+"""-preauthkey-table'>
                    <thead>
                        <tr>
                            <td>ID</td>
                            <td class='tooltipped' data-tooltip='Click an Auth Key Prefix to copy it to the clipboard'>Key Prefix</td>
                            <td><center>Reusable</center></td>
                            <td><center>Used</center></td>
                            <td><center>Ephemeral</center></td>
                            <td><center>Usable</center></td>
                            <td><center>Actions</center></td>
                        </tr>
                    </thead>
                """
    for key in preauth_keys["preAuthKeys"]:
        # Get the key expiration date and compare it to now to check if it's expired:
        # Set the current timezone and local time
        timezone         = pytz.timezone(os.environ["TZ"] if os.environ["TZ"] else "UTC")
        local_time       = timezone.localize(datetime.now())
        expiration_parse = parser.parse(key["expiration"])
        key_expired = True if expiration_parse < local_time else False
        expiration_time  = str(expiration_parse.strftime('%A %m/%d/%Y, %H:%M:%S'))+" "+str(timezone)

        key_usable = False
        if key["reusable"] and not key_expired: key_usable = True
        if not key["reusable"] and not key["used"] and not key_expired: key_usable = True
        
        # Class for the javascript function to look for to toggle the hide function
        hide_expired = "expired-row" if not key_usable else ""

        btn_reusable  = "<i class='pulse material-icons tiny blue-text text-darken-1'>fiber_manual_record</i>"   if key["reusable"]  else ""
        btn_ephemeral = "<i class='pulse material-icons tiny red-text text-darken-1'>fiber_manual_record</i>"    if key["ephemeral"] else ""
        btn_used      = "<i class='pulse material-icons tiny yellow-text text-darken-1'>fiber_manual_record</i>" if key["used"]      else ""
        btn_usable    = "<i class='pulse material-icons tiny green-text text-darken-1'>fiber_manual_record</i>"  if key_usable       else ""

        # Other buttons:
        btn_delete    = "<span href='#card_modal' data-tooltip='Expire this PreAuth Key' class='btn-small modal-trigger badge tooltipped white-text red' onclick='load_modal_expire_preauth_key(\""+user_name+"\", \""+str(key["key"])+"\")'>Expire</span>" if key_usable else ""
        tooltip_data  = "Expiration:  "+expiration_time

        # TR ID will look like "1-albert-tr"
        preauth_keys_collection = preauth_keys_collection+"""
            <tr id='"""+key["id"]+"""-"""+user_name+"""-tr' class='"""+hide_expired+"""'>
                <td>"""+str(key["id"])+"""</td>
                <td  onclick=copy_preauth_key('"""+str(key["key"])+"""') class='tooltipped' data-tooltip='"""+tooltip_data+"""'>"""+str(key["key"])[0:10]+"""</td>
                <td><center>"""+btn_reusable+"""</center></td>
                <td><center>"""+btn_used+"""</center></td>
                <td><center>"""+btn_ephemeral+"""</center></td>
                <td><center>"""+btn_usable+"""</center></td>
                <td><center>"""+btn_delete+"""</center></td>
            </tr>
        """

    preauth_keys_collection = preauth_keys_collection+"""</table>
        </li>
        """
    return preauth_keys_collection

def oidc_nav_dropdown(user_name, email_address, name):
    app.logger.info("OIDC is enabled.  Building the OIDC nav dropdown")
    html_payload = """
        <!-- Dropdown Structure -->
        <ul id="dropdown1" class="dropdown-content dropdown-oidc">
            <ul class="collection dropdown-oidc-collection">
                <li class="collection-item dropdown-oidc-avatar avatar">
                    <i class="material-icons circle">email</i>
                    <span class="dropdown-oidc-title title">Email</span>
                    <p>"""+email_address+"""</p>
                </li>
                <li class="collection-item dropdown-oidc-avatar avatar">
                    <i class="material-icons circle">person_outline</i>
                    <span class="dropdown-oidc-title title">Username</span>
                    <p>"""+user_name+"""</p>
                </li>
            </ul>
        <li class="divider"></li>
            <li><a href="logout"><i class="material-icons left">exit_to_app</i> Logout</a></li>
        </ul>
        <li>
            <a class="dropdown-trigger" href="#!" data-target="dropdown1">
                """+name+""" <i class="material-icons right">account_circle</i>
            </a>
        </li>
    """
    return Markup(html_payload)

def oidc_nav_mobile(user_name, email_address, name):
# https://materializecss.github.io/materialize/sidenav.html
    html_payload = """
         <li><hr><a href="logout"><i class="material-icons left">exit_to_app</i>Logout</a></li>
    """
    return Markup(html_payload)