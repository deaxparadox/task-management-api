from collections import OrderedDict
from uuid import uuid4
from importlib import import_module

from flask import (
    Blueprint,
    jsonify,
    request
)
from flask.views import MethodView
from flask_jwt_extended import (
    current_user,
    get_jwt_identity,
    create_access_token,
    create_refresh_token,
    jwt_required,
)

from ..serializer import (
    UserRegisterSerializer, 
    UserLoginSerializer,
    PRLoggedUserSerailizer
)
from ..utils import (
    account_activation_link, 
    password_reset_link,
    encode_string,
    decode_string,
    account_activation_otp
)
from ..utils.user import UserType
from ..database import db_session
from ..models.user import User
from ..models.address import Address
from ..models.validation import Validation
from ..utils.message import message_collector
from ..utils.validation import password_validation
from ..utils.mail import (
    check_mail_exists, 
    send_account_activation_mail,
    send_password_reset_mail
)
from ..cache import cache


bp = Blueprint("auth", __name__, url_prefix="/api/auth")

class RegisterView(MethodView):
    
    def __init__(self, model):
        self.model: User = model
        self.mc = message_collector()
        
    def check_user_exists(self, username: str) -> bool:
        query = db_session.query(User).where(self.model.username==username).all()
        if len(query) > 0:
            return True
        return False
    
    def get_user_type(self, value):
        """
        Return appropriate User roles
        """
        if UserType.Employee.value == value:
            return UserType.Employee
        if UserType.TeamLead.value == value:
            return UserType.TeamLead
        if UserType.Manager.value == value:
            return UserType.Manager
        return 0
    
    default_opt = "123432"
    
    def otp(self, user: User):
        
        # set otp in cache
        cache.set(f"{user.username}_otp", self.default_opt)
        
        mail_message = f"You OTP for activating the account is: {self.default_opt}"
        if send_account_activation_mail(user.email, mail_message):
            self.mc("OTP has been sent the your email address")
        else:
            self.mc("Unable to send email contact administrator")
        
        return jsonify(message=self.mc()), 201
    
    def post(self):
        opt = request.args.get("opt")
        
        
        try:
            serializer = UserRegisterSerializer(**request.json)
        except (AttributeError, TypeError) as e:
            # generated by serialier
            return jsonify(message="Invalid fields username, role, email and password"), 400
        
        # check user existence
        if self.check_user_exists(serializer.username):
            return jsonify(message="User name taken"), 302
        
        # check email existence
        if check_mail_exists(serializer.email):
            return jsonify(message="Email already exists"), 302
        
        # check password length
        passwd_status, passwd_message = password_validation(serializer.password)
        if not passwd_status:
            return jsonify(message=passwd_message), 400
        
        # check user role
        user_role = self.get_user_type(serializer.role)
        if not user_role:
            return jsonify(message="Invalid user role."), 400
        
        # add user
        user = self.model(
            username=serializer.username, 
            password=User.make_passsword(serializer.password),
            email=serializer.email
        )
        user.role = user_role
        user.account_activation_id = uuid4()
        db_session.add(user)
        db_session.commit()
        
        self.mc("User created successfully")
        
        if opt == "yes":
            return self.otp(user)
        
        mail_message = (
            "Click on the following link to activate the account:" +
            account_activation_link(request, user)
        )
        if send_account_activation_mail(user.email, mail_message):
            self.mc("Verification email has been sent to your email address ")
        else:
            self.mc("Unable to send email contact administrator")
        
        return jsonify(
            message=self.mc(),
        ), 201

class AccountActivateView(MethodView):
    def get(self, user_id, act_id):
        user = db_session.query(User).filter_by(id=user_id, account_activation_id=act_id).one_or_none()
        if not user:
            return jsonify(message="Invalid user and activation ID"), 400
        user.account_activation = True
        db_session.add(user)
        db_session.commit()
        return jsonify(message="User account successfully activated")

class AccountActivateOTPView(MethodView):
    def post(self):
        username = request.json.get('username')
        user_otp = request.json.get("otp")
        
        if not username or not user_otp:
            return jsonify(message="Required username and otp"), 200
        
        otp = cache.get(f"{username}_otp")
        
        if not otp:
            return jsonify(message="OTP not found, user account already activated.")
        
        if otp == user_otp:
            cache.delete(f"{username}_otp")
            return jsonify(message="User successfully activated"), 200
        
        return jsonify(message="Incorrect OTP"), 400

class LoginView(MethodView):
    def __init__(self, model):
        self.model = model
        
    def post(self):
        
        try:
            serializer = UserLoginSerializer(**request.json)
        except (AttributeError, TypeError) as e:
            # generated by serialier
            return jsonify(message="Required username and password"), 400
        
        # get user active and account_activation check
        user = db_session.query(User).filter(User.username==serializer.username).one_or_none()
        if not user or not user.active:
            return jsonify(message="User not found"), 404
        
        # account activation check
        if not user.account_activation:
            return jsonify(message="Please check you email, verfication link has already been sent to your email address"), 302
        
        # check password
        if not user.check_password(serializer.password):
            return jsonify(message="Invalid username and password"), 400
        
        data = OrderedDict()
        data["message"] = "User successfully logged in"
        data["access_token"] = create_access_token(identity=user, fresh=True)
        data["refresh_token"] = create_refresh_token(identity=user)
        
        return jsonify(data), 200


def register_api(app: Blueprint, model: User, name: str, view_class=None):
    app.add_url_rule(
        f'/{name}', 
        view_func=view_class.as_view(f"user-{name}", model)
    )
        

# Method views register
register_api(bp, User, 'register', RegisterView)
register_api(bp, User, 'login', LoginView)
bp.add_url_rule("/otp", view_func=AccountActivateOTPView.as_view("user-activation-otp"))
bp.add_url_rule("/register/<int:user_id>/<act_id>", view_func=AccountActivateView.as_view("user-activation"))


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh_token():
    """
    Refresh user token
    """
    identity = get_jwt_identity()
    
    user = db_session.query(User).filter_by(id=int(identity)).filter_by(active=True).one_or_none()
    if not user:
        return jsonify(message="Invalid refresh token"), 401
    
    access_token = create_access_token(identity=user, fresh=False)
    
    return jsonify(access_token=access_token)


@bp.post("/password-reset")
@jwt_required(fresh=True)
def reset_logged_user_password():
    """
    Reset the password of logged in user.
    """
    
    try:
        password_serializer = PRLoggedUserSerailizer(**request.json)
    except (AttributeError, TypeError) as e:
        return jsonify(message=str(e)), 400
    
    # 
    pass_status, pass_message = password_validation(password_serializer.new_password)
    if not pass_status:
        return jsonify(message=pass_message), 400
    
    # check last password
    if not current_user.check_password(password_serializer.last_password):
        return jsonify(message="Your last password is incorrect."), 400
    
    current_user.password = User.make_passsword(password_serializer.new_password)
    db_session.add(current_user)
    db_session.commit()
    
    return jsonify(message="Password changed successfully"), 202
    
    
@bp.post("/password-reset-unknown")
def reset_unknown_user_password():
    """
    Reset password of unknown user. Email required.
    """
    mc = message_collector()
    try:
        email = request.json.get("email")
    except (AttributeError, TypeError) as e:
        return jsonify(message=str(e)), 400
    
    try:
        user = db_session.query(User).filter_by(email=email, active=True).one_or_none()
    except Exception as e:
        # multiple email association
        mc(str(e))
        return jsonify(message=mc()), 400
    
    # user with email found
    if user:
        validation = Validation(
            id = uuid4(),
            user_id=user.id
        )
        db_session.add(validation)
        db_session.commit()
        
        encoded_string = encode_string(email=email, validation_id=validation.get_validation_id)
        
        link =(
            "Click on the following link to update password:" + 
            password_reset_link(request, encoded_string)
        )
        if send_password_reset_mail(user.email, link):
            mc("Password reset link has been sent to your email address ")
        else:
            mc("Unable to send email contact administrator")

        return jsonify(
            message=mc()
        ), 202
        
    # email not found
    return jsonify(message="User not found"), 400


@bp.post("/password-reset-unknown/<val_id>")
def reset_password_using_validation_id(val_id: str):    
    try:
        
        decode_data = decode_string(val_id)
        
        validation: Validation = db_session.query(Validation).get({"id": decode_data.get("validation_id")})
        if not validation or not validation.active:
            raise ValueError("Invalid validation ID")
        
        password = request.json.get("password")
        email = decode_data.get('email')
        if not password or not email:
            return jsonify(message="Invalid email and password details"), 400
        
        # check password
        passwd_status, passwd_message = password_validation(password)
        if not passwd_status:
            return jsonify(message=passwd_message), 400
        
        user: User = db_session.query(User).get({"id":validation.get_user_id})
        # email check
        if user.email != email:
            return jsonify(message="Email ID doesn't match"), 400
            
        user.password = User.make_passsword(password)
        
        db_session.add(user)
        db_session.commit()
        
        validation.active = False
        db_session.add(validation)
        db_session.commit()
        
    except Exception as e:
        return jsonify(message=[
            "Invalid link",
            str(e)
        ]), 400
    
    return jsonify(message="Password reset successfully"), 202



@bp.delete("/delete")
@jwt_required(fresh=True)
def soft_delete_user():
    """
    Soft delete a user.
    """
    
    if not current_user.active:
        return jsonify(message="User already deleted"), 302
     
    current_user.active = False
    db_session.add(current_user)
    db_session.commit()
    return jsonify(message=f"User {current_user.username} successfully deleted"), 302
