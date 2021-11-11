import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import pymongo
import secrets


MONGODB_URI = os.environ.get("MONGODB_URI")


client = pymongo.MongoClient(MONGODB_URI)

db = client['sdt_ext']
collection_ticketinfo = db['ticket_information']
collection_users = db['users']

app = Flask(__name__)
CORS(app)

def check_args(args):
    if 'ticket_no' in args and 'useremail' in args and 'user_key' in args and 'picked' in args and 'worked_on' in args:
        return True
    else:
        return False

def check_args_register(args):
    if 'useremail' in args and 'user_key' in args:
        return True
    else:
        return False

def create_document(ticket_no, useremail, picked, worked_on):
    return {
        "ticket_no": ticket_no,
        "useremail": useremail.lower(),
        "picked": True if picked.lower() == "true" else False,
        "worked_on": worked_on
    }

def get_user(useremail):
    doc = collection_users.find_one({"useremail": useremail}, {"_id":0})
    return doc


def validate_user(useremail, user_key):
    doc = collection_users.find_one({"useremail": useremail, "user_key": user_key}, {"_id":0})
    return doc


def get_ticket(ticket_no):
    doc = collection_ticketinfo.find_one({"ticket_no": ticket_no}, {"_id":0})
    return doc


def update_ticket(ticket_no, useremail, picked, worked_on):
    replace_this = {"ticket_no": ticket_no}
    with_this = {"$set": create_document(
        ticket_no=ticket_no,
        useremail=useremail.lower(),
        picked=picked,
        worked_on=worked_on)
    }
    modified = collection_ticketinfo.update_one(replace_this, with_this)
    return modified.matched_count

def get_picked_tickets(worked_on):
    docs = collection_ticketinfo.find({"worked_on": worked_on, "picked": True}, {"_id":0})
    return [ticket['ticket_no'] for ticket in docs]

def generate_user_key(length):
    return secrets.token_urlsafe(length)

def get_ticket_owner(ticket_no):
    doc = collection_ticketinfo.find_one({"ticket_no": ticket_no}, {"_id":0})
    return doc['useremail'] if doc else ''

def generate_error(msg):
    return {
        "success": False,
        "error": True,
        "error_msg": msg
    }

def generate_success(msg):
    return {
        "success": True,
        "msg": msg,
        "error": False,
        "error_msg": ""
    }

@app.route("/", methods=['GET'])
def index():
    return jsonify(generate_success("SDT-EXT-API v.1"))

def get_error(err_code):

    error_responses = {
        "404": "Resource not found. Please refer to the documentation.",
        "419": "The requested resource is missing required arguments. Please refer to the documentation.",
        "420": "The requested resource does not support one or more of the given parameters. Please refer to the documentation.",
        "405": "This method type is not currently supported. Please refer to the documentation.",
        "500": "Internal Server Error"
    }
    return error_responses[err_code]

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify(generate_error(get_error("500")))

@app.errorhandler(404)
def invalid_route(e):
    return jsonify(generate_error(get_error("404")))

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify(generate_error(get_error("405")))


# add/update ticket
@app.route("/add", methods=['GET'])
def add_ticket():
    # check if parameters aren't missing
    if not check_args(request.args):
        return jsonify(generate_error("Invalid parameters"))

    # invalid useremail/user key
    if not validate_user(request.args['useremail'], request.args['user_key']):
        return jsonify(generate_error("Invalid useremail or user key provided"))

    status = {}            
    current_ticket = get_ticket(request.args['ticket_no'])
    # if already exists
    if current_ticket:
        # if different user trying to pick an already picked ticket
        if (request.args['useremail'].lower() != current_ticket['useremail']) and (current_ticket['picked'] == True):
            status = generate_error(f"{current_ticket['useremail']} has to drop this ticket")
    
        else:
            updated_count = update_ticket(
                request.args['ticket_no'],
                request.args['useremail'],
                request.args['picked'],
                request.args['worked_on']
            )
            status = generate_success("Updated successfully")
            status["updated"] = True
            status["updated_count"] = updated_count
    # New Ticket
    else:
        # user trying to drop a ticket that doesn't exist
        if request.args['picked'].lower() == 'false':
            return jsonify(generate_error("Ticket doesn't exist"))

        try:
            collection_ticketinfo.insert_one(create_document(
                ticket_no=request.args['ticket_no'],
                useremail=request.args['useremail'],
                picked=request.args['picked'],
                worked_on=request.args['worked_on']
                ))
            status = generate_success("Added successfully")
            status['new_entry'] = True
        except Exception as ex:
            status = generate_error(ex)

    return jsonify(status)    
    

# register new user
@app.route("/register", methods=['GET'])
def register():
    # invalid parameters
    if not check_args_register(request.args):
        return jsonify(generate_error("Invalid Parameters"))

    useremail = request.args['useremail']
    user_key = request.args['user_key']
    status = {}

    # already exists and re-registering with invalid credentials
    if get_user(useremail):
        if not user_key:
            return jsonify(generate_error("No user key provided"))

        user = validate_user(useremail, user_key)
        print(user)
        if not user:
            return jsonify(generate_error("Invalid useremail/user key pair"))
        
        status = generate_success("Existing user re-registration successful")
        status['user_key'] = user['user_key']
        
    else:
        # new user
        try:
            new_key = generate_user_key(32)
            collection_users.insert_one({
                "useremail": useremail,
                "user_key": new_key
            })
            status = generate_success("Registration Successful")
            status["user_key"] = new_key
        except Exception as ex:
            status = generate_error(ex)       

    return jsonify(status)

@app.route("/tickets", methods=['GET'])
def picked_tickets():
    if "worked_on" not in request.args:
        return jsonify(generate_error("Invalid Parameters"))

    worked_on = request.args['worked_on']
    status = {}

    if not worked_on:
        return jsonify(generate_error("worked_on cannot be empty"))

    tickets = get_picked_tickets(worked_on)
    status = generate_success(f"Query successful")
    status["worked_on"] = worked_on
    status['ticket_no'] = tickets

    return status

@app.route("/who", methods=['GET'])
def ticket_owner():
    if "ticket_no" not in request.args:
        return jsonify(generate_error("Invalid Parameters"))

    ticket_no = request.args['ticket_no']

    if not ticket_no:
        return jsonify(generate_error("Ticket number cannot be empty"))
    status={}
    ticket = get_ticket(ticket_no)

    if not ticket:
        return jsonify(generate_error("Ticket not found"))
    
    owner = ticket['useremail']

    if not owner or ticket['picked'] == False:
        status = generate_success("No owner")
        status['useremail'] = None
    else:
        status = generate_success("Owner found")
        status['useremail'] = owner

    return status
        

if __name__ == "__main__":
    # app.run(debug=True, host="0.0.0.0", port=5000)
    app.run(debug=False, port=8080)
