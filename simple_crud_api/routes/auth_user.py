from collections import OrderedDict

from flask import (
    Blueprint,
    request,
    jsonify
)
from flask.views import MethodView
from flask_jwt_extended import (
    current_user,
    jwt_required,
)

from simple_crud_api.database import db_session
from ..models.user import User
from ..models.address import Address
from ..serializer import (
    UserProfileSerializer,
    UserUpdateSerializer,
    AddressUpdateSerializer
)
from ..utils.message import message_collector
from ..utils.models import get_fields
from ..utils.validation import phone_number_validation
from ..utils.mail import (
    check_mail_exists,
    check_phone_exists
)

bp = Blueprint("auth_user", __name__, url_prefix="/api/user")

@bp.route("", methods=["GET"])
@jwt_required()
def user_detail_view():
    """
    Get user details
    """
    data = current_user.to_dict()
    address = db_session.query(Address).filter_by(user_id=current_user.id).one_or_none()
    if isinstance(address, Address):
        data['address'] = address.to_dict()
    return jsonify(details=data)




@bp.route("/profile", methods=["POST"])
@jwt_required(fresh=True)
def update_profile():
    """
    All the fields are required for profile endpoints.
    
    All non-optional fields are required from User and Address models.
    """
    
    messages = message_collector(only_list=True)
    
    
    # one-time profile update
    if current_user.phone != None and current_user.first_name != None and current_user.last_name != None:
        messages("Profile already updated")
        messages("To update user details, please visited the update endpoint.")
        return jsonify(message=messages()), 200
    
    try:
        serializer = UserProfileSerializer(**request.json)
    except (AttributeError, TypeError) as e:
        messages("Invalid user details")
        messages(str(e))
        return jsonify(message=messages()), 400
    
    # phone number validation
    if not phone_number_validation(serializer.phone):
        return jsonify(message="Enter a valid phone number")
    if check_phone_exists(serializer.phone):
        return jsonify(message="Phone number already in use.")
    
    # removed address from serializer
    address_details = serializer.address
    
    # return error if any of the fields is None
    keys: list = list(serializer.__dict__.keys())
    keys.remove("address")
    
    # Update user details
    for k in keys:
        value = getattr(serializer, k, None)
        if value is None:
            messages("All fields are required. Fields (%s)" % ', '.join([k for k in keys]))
            return jsonify(message=messages()), 400
        setattr(current_user, k, value)
        
    db_session.add(current_user)
    try:
        db_session.commit()
    except Exception as e:
        messages(str(e))
        return jsonify(messages=messages()), 400
    
    # check for address existence of current user
    address = db_session.query(Address).filter_by(user_id=current_user.id).one_or_none()
    
    # update details
    if address_details:
        address_fields = get_fields(Address)
        for x in ['id', "user_id"]:
            address_fields.remove(x)
        try:
            # address exists
            if isinstance(address, Address):
                address.line1=address_details['line1']
                address.city=address_details['city']
                address.state=address_details['state']
                address.country=address_details['country']
                address.pincode=address_details['pincode']
            else:
                # address not exists
                address = Address(
                    line1=address_details['line1'],
                    city=address_details['city'],
                    state=address_details['state'],
                    country=address_details['country'],
                    pincode=address_details['pincode']
                )
        except Exception as e:
            messages("required fields in addesss (%s)" % ", ".join(address_fields))
            messages(str(e))
            return jsonify(message=messages()), 400
        
        address.user_id = current_user.id
        db_session.add(address)
        db_session.commit()
    
    # build response
    data = current_user.to_dict()
    if address_details:
        data['address'] = address.to_dict()
        
    return jsonify(details=data), 202



class UpdateView(MethodView):
    """
    Partial update
    """
    
    def __init__(self):
        self.mc = message_collector()
        
    def get_keys(self, d: dict):
        return d.keys()
    
    def empty_user_data(self, user_data: dict) -> bool:
            if not user_data or len(user_data.keys()) == 0:
                return True
            return False
    
    address = False
    @jwt_required(fresh=True)
    def post(self):
        
        # If the user have not updated the profile.
        # then return a response to update the profile.
        if current_user.email is None:
            return jsonify(message="Update your profile"), 401
        
        user_data: dict | None = request.json
        
        try:
            address_data: dict | None = user_data.pop("address", None)
            # print(address_data, user_data)
            if address_data:
                self.address = True
            
            address_serializer = None
            user_serializer = None
            
            if address_data:
                address_serializer = AddressUpdateSerializer(**address_data)

            user_serializer = UserUpdateSerializer(**user_data)
        
        except Exception as e:
            self.mc(str(e))
            return jsonify(message=self.mc()), 400
        
        # check for empty request data
        if self.empty_user_data(user_data) and self.empty_user_data(address_data):
            return jsonify(message="Invalid request data"), 400
        
        # phone number validation
        # email existence
        if user_serializer:
            if user_serializer.email and check_mail_exists(user_serializer.email):
                return jsonify(message="Email already existss"), 302
            if user_serializer.phone:
                if not phone_number_validation(user_serializer.phone):
                    return jsonify(message='Invalid phone number'), 400
                if check_phone_exists(user_serializer.phone):
                    return jsonify(message="Phone number already exists"), 302
        
        if self.address:
            address_query = db_session.query(Address).filter_by(user_id=current_user.id).one_or_none()
            if address_query:
                # address update
                for k in self.get_keys(address_data):
                    setattr(address_query, k, getattr(address_serializer, k))
                    db_session.add(address_query)
                    db_session.commit()  
            else:
                # address register
                address_query = Address()
                required_fields = address_query.get_reqired_fields()
                for k in self.get_keys(address_data):
                    if k not in required_fields:
                        self.mc("Address doesn't exists")
                        self.mc("Following fields are required (%s)" % ", ".join(required_fields))
                        return jsonify(message=self.mc()), 400
                    setattr(address_query, k, getattr(address_serializer, k))
                address_query.user_id = current_user.id
                db_session.add(address_query)
                db_session.commit()
    
        if user_serializer:
            for k in self.get_keys(user_data):
                setattr(current_user, k, getattr(user_serializer, k))
            db_session.add(current_user)
            db_session.commit()
        
        return jsonify(message="Updated successful"), 202
    
bp.add_url_rule(
    "/update", 
    view_func=UpdateView.as_view('user-update')
)