import os
import logging
from flask import Blueprint, render_template, request, redirect, session, jsonify, flash, url_for
from auth.service import (
    approve_child_account,
    login_user,
    profile_exists,
    get_parent_verification_data,
    ensure_token_parent_pending,
    process_parent_verification,
    get_child_approval_details,
    process_child_decision
)
from auth.parent_email_otp import begin_parent_registration, verify_parent_email_otp, resend_parent_email_otp
from services.usage import start_session, close_session
from database.connection import fetch_one, execute
from extensions import limiter, csrf
from decorators import child_required, login_required
from services.i18n import set_language, LANGUAGES

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, template_folder='templates')


def _set_session(user, method='PASSWORD'):
    session.clear()
    session.permanent = True
    session['user_id'] = user['user_id']
    session['role'] = user['role']
    session['full_name'] = user['full_name']
    session['mode'] = 'KIDS' if user['role'] == 'CHILD' else 'PARENT'
    execute('INSERT INTO login_activity(user_id,login_method,success) VALUES(%s,%s,TRUE)', (user['user_id'], method))
    if user['role'] == 'CHILD':
        us = start_session(user['user_id'])
        session['usage_session_key'] = str(us['session_key'])
    elif user['role'] == 'PARENT':
        execute('UPDATE parent_child_map SET parent_id=%s, verified_parent_id=COALESCE(verified_parent_id,%s) WHERE LOWER(parent_email)=LOWER(%s) AND parent_id IS NULL', (user['user_id'], user['user_id'], user['email']))


def _dest(user):
    if user['role'] == 'CHILD':
        if not profile_exists(user['user_id']):
            try:
                from child.service import create_child_profile
                create_child_profile(user['user_id'], {'full_name': user.get('full_name') or user.get('username') or 'Student', 'bio': "Hey! I'm on LittleNet 🌟"})
            except Exception:
                pass
        return '/child/dashboard/'
    if user['role'] == 'PARENT':
        return '/parent/dashboard/'
    return '/admin/'


def _pending_parent():
    uid = session.get('pending_parent_user_id')
    if not uid:
        return None
    return fetch_one("SELECT * FROM users WHERE user_id=%s AND role='PARENT' AND account_status='PENDING_APPROVAL'", (uid,))


def _mask_email(email):
    email = (email or '').strip()
    if '@' not in email:
        return email
    local, domain = email.split('@', 1)
    shown = local[:2] if len(local) > 2 else local[:1]
    return f"{shown}{'*' * max(2, len(local)-len(shown))}@{domain}"


def _resume_parent_verification(user):
    session.clear()
    session.permanent = True
    otp = fetch_one('SELECT verified_at FROM parent_email_otps WHERE user_id=%s', (user['user_id'],))
    if otp and otp.get('verified_at'):
        # Email OTP is the complete parent verification: activate and sign in.
        execute(
            "UPDATE users SET account_status='ACTIVE' WHERE user_id=%s AND role='PARENT' AND account_status='PENDING_APPROVAL'",
            (user['user_id'],),
        )
        active = fetch_one('SELECT * FROM users WHERE user_id=%s', (user['user_id'],))
        if active and active.get('account_status') == 'ACTIVE':
            _set_session(active)
            return redirect('/parent/dashboard/')
    session['pending_parent_user_id'] = user['user_id']
    session['pending_parent_email'] = user.get('email')
    session['pending_parent_email_verified'] = False
    return redirect('/verify-parent-email/')


@auth_bp.route('/')
def mode_select():
    if session.get('user_id'):
        if session.get('role') == 'CHILD':
            return redirect('/child/dashboard/' if profile_exists(session['user_id']) else '/child/create-profile/')
        elif session.get('role') == 'PARENT':
            return redirect('/parent/dashboard/')
        elif session.get('role') == 'ADMIN':
            return redirect('/admin/')
    mode = request.args.get('mode', 'kids').lower()
    return render_template('login.html', mode=mode)


@auth_bp.route('/login/', methods=['GET', 'POST'])
@limiter.limit('30 per minute')
def login():
    mode = request.args.get('mode', 'kids').lower()
    if request.method == 'POST':
        ident = request.form.get('email', '') or request.form.get('username', '')
        user = login_user(ident, request.form.get('password', ''))
        req_mode = request.form.get('mode', 'kids')
        if not user:
            return render_template('login.html', mode=req_mode, error='Invalid username/email or password.'), 401

        if user['role'] == 'PARENT':
            if user['account_status'] == 'PENDING_APPROVAL':
                return _resume_parent_verification(user)
            if user['account_status'] != 'ACTIVE':
                return render_template('login.html', mode='parent', error='Parent account is suspended or inactive.'), 403
            _set_session(user)
            return redirect('/parent/dashboard/')

        if user['role'] == 'ADMIN':
            _set_session(user)
            return redirect('/admin/')

        if user['account_status'] == 'PENDING_APPROVAL':
            mapping = fetch_one('SELECT approval_token, verification_token FROM parent_child_map WHERE child_id=%s', (user['user_id'],))
            tok = mapping['verification_token'] if mapping and mapping.get('verification_token') else (mapping['approval_token'] if mapping else None)
            return render_template('login.html', mode='kids',
                                   error='This child account is waiting for parent identity verification & approval.',
                                   approval_token=tok), 403
        if user['account_status'] != 'ACTIVE':
            return render_template('login.html', mode='kids', error='Account is suspended or inactive.'), 403
        _set_session(user)
        return redirect(_dest(user))
    return render_template('login.html', mode=mode)


@auth_bp.route('/register-child', methods=['GET', 'POST'])
@auth_bp.route('/register-child/', methods=['GET', 'POST'])
@limiter.limit('100 per hour')
def register_page():
    return redirect('/register-parent/?note=parents_create_child_accounts')


def _render_token_verified_result(token, child_data, result):
    """Shared completion step for the token guardian flow after the parent's
    email ownership is proven: run verification, sign in, and route onward."""
    if not result.get('success'):
        # Both call sites guard on success first, so this branch is latent;
        # render an error page rather than returning None so no caller can
        # ever produce an empty response from this helper.
        return render_template(
            'approval_success.html', is_error=True, title='Verification Failed',
            message=result.get('error') or 'Parent verification could not be completed. Please try the verification link again.',
            button_url='/login/', button_text='Go to Login'
        ), 400
    parent_row = fetch_one('SELECT * FROM users WHERE user_id=%s', (result['parent_id'],))
    if parent_row and parent_row.get('account_status') == 'ACTIVE':
        _set_session(parent_row)

    if result.get('auto_approved'):
        return render_template(
            'approval_success.html', is_verified=True, title='Child Account Approved & Active!',
            message=f"You have successfully verified your parent account and activated {child_data.get('child_name')}'s account. They can now log in safely!",
            button_url='/parent/dashboard/', button_text='Go to Parent Dashboard'
        )
    return redirect(f"/parent/approve-child/{result['approval_token']}/")


@auth_bp.route('/verify-parent/<token>/', methods=['GET', 'POST'])
@limiter.limit('30 per minute')
def verify_parent(token):
    child_data = get_parent_verification_data(token)
    if not child_data:
        return render_template(
            'approval_success.html', is_error=True, title='Invalid Verification Link',
            message='This parent identity verification link is invalid or has expired.',
            button_url='/login/', button_text='Go to Login'
        ), 404

    if child_data.get('approved'):
        return render_template(
            'approval_success.html', is_verified=True, title='Account Already Approved!',
            message=f"The account for {child_data.get('child_name')} has already been verified and is active.",
            button_url='/login/?mode=kids', button_text='Go to Child Login'
        )

    parent_user = fetch_one("SELECT user_id, account_status FROM users WHERE LOWER(email)=%s AND role='PARENT'", (child_data['parent_email'].lower(),))
    parent_exists = bool(parent_user)

    if request.method == 'POST':
        # Email-OTP-only guardian verification: validate the form, ensure a
        # parent account exists, then prove email ownership with a 6-digit OTP.
        prep = ensure_token_parent_pending(token, request.form)
        if not prep.get('success'):
            return render_template('parent_verify.html', child=child_data, parent_exists=parent_exists, error=prep.get('error')), 400

        if prep.get('already_active'):
            # Already-verified parent account: complete verification directly.
            form = dict(request.form)
            result = process_parent_verification(token, form)
            if not result.get('success'):
                return render_template('parent_verify.html', child=child_data, parent_exists=parent_exists, error=result.get('error')), 400
            return _render_token_verified_result(token, child_data, result)

        ok, error, dev_code = resend_parent_email_otp(prep['parent_id'], with_code=True)
        if not ok:
            return render_template('parent_verify.html', child=child_data, parent_exists=parent_exists, error=error), 400
        session['pending_token_verification'] = token
        session['pending_token_parent_id'] = prep['parent_id']
        return redirect(f'/verify-parent/{token}/otp/')

    return render_template('parent_verify.html', child=child_data, parent_exists=parent_exists)


@auth_bp.route('/verify-parent/<token>/otp/', methods=['GET', 'POST'])
@limiter.limit('30 per minute')
def verify_parent_token_otp(token):
    """Second step of the token guardian flow: verify the 6-digit email OTP,
    then complete parent verification and child approval."""
    if session.get('pending_token_verification') != token:
        return redirect(f'/verify-parent/{token}/')
    parent_id = session.get('pending_token_parent_id')
    child_data = get_parent_verification_data(token)
    parent = fetch_one("SELECT * FROM users WHERE user_id=%s AND role='PARENT'", (parent_id,)) if parent_id else None
    if not child_data or not parent:
        for key in ('pending_token_verification', 'pending_token_parent_id'):
            session.pop(key, None)
        return redirect(f'/verify-parent/{token}/')

    if request.method == 'POST':
        if 'resend' in request.form:
            ok, error = resend_parent_email_otp(parent_id)
            return render_template(
                'parent_token_otp.html', child=child_data,
                masked_email=_mask_email(parent['email']),
                error=error if not ok else None,
                notice='A new 6-digit code was sent.' if ok else None,
            ), (200 if ok else 400)

        ok, error, _ = verify_parent_email_otp(parent_id, request.form.get('otp', ''))
        if not ok:
            return render_template(
                'parent_token_otp.html', child=child_data,
                masked_email=_mask_email(parent['email']), error=error,
            ), 400

        for key in ('pending_token_verification', 'pending_token_parent_id'):
            session.pop(key, None)
        result = process_parent_verification(token, {'parent_name': parent.get('full_name') or '', 'consent': '1', 'auto_approve': '1'})
        if not result.get('success'):
            return render_template(
                'parent_token_otp.html', child=child_data,
                masked_email=_mask_email(parent['email']), error=result.get('error'),
            ), 400
        return _render_token_verified_result(token, child_data, result)

    return render_template('parent_token_otp.html', child=child_data, masked_email=_mask_email(parent['email']))


@auth_bp.route('/parent/approve-child/<token>/', methods=['GET', 'POST'])
@limiter.limit('30 per minute')
def parent_approve_child(token):
    if 'user_id' not in session or session.get('role') != 'PARENT':
        return redirect(f'/login/?mode=parent&next=/parent/approve-child/{token}/')

    logged_in_parent_id = session['user_id']
    check = get_child_approval_details(token, logged_in_parent_id)

    if request.method == 'POST':
        if not check.get('valid'):
            reason = check.get('reason', 'UNKNOWN')
            if reason == 'TOKEN_ALREADY_USED':
                return render_template('approval_success.html', is_verified=True, title='Account Already Approved!', message='This child account has already been approved and is fully active.', button_url='/parent/dashboard/', button_text='Go to Parent Dashboard')
            return render_template('approval_success.html', is_error=True, title='Action Failed', message=f'Cannot process request: {reason}', button_url='/parent/dashboard/', button_text='Go to Parent Dashboard'), 403

        decision = request.form.get('decision', 'APPROVE')
        rejection_reason = request.form.get('rejection_reason')
        result = process_child_decision(token, logged_in_parent_id, decision, rejection_reason)
        if result.get('success'):
            if result.get('action') == 'APPROVED':
                return render_template('approval_success.html', is_verified=True, title='Child Account Approved!', message=f"You have successfully verified and activated {result.get('child_name')}'s account. Your parental supervision controls are now active.", button_url='/parent/dashboard/', button_text='Go to Parent Dashboard')
            return render_template('approval_success.html', is_error=True, title='Account Declined', message=f"You have declined the registration request for {result.get('child_name')}.", button_url='/parent/dashboard/', button_text='Go to Parent Dashboard')
        return render_template('approval_success.html', is_error=True, title='Approval Failed', message=result.get('error', 'An unknown error occurred.'), button_url='/parent/dashboard/', button_text='Go to Parent Dashboard'), 400

    if not check.get('valid'):
        reason = check.get('reason', 'UNKNOWN')
        if reason == 'TOKEN_ALREADY_USED':
            return render_template('approval_success.html', is_verified=True, title='Account Already Approved!', message='This child account has already been approved and is active.', button_url='/parent/dashboard/', button_text='Go to Parent Dashboard')
        return render_template('approval_success.html', is_error=True, title='Invalid or Expired Link', message=f'This approval request cannot be opened: {reason}', button_url='/parent/dashboard/', button_text='Go to Parent Dashboard'), 400

    return render_template(
        'approve_child.html', valid=True, child=check['child'], parent=check['parent'],
        verification=check.get('verification', {'status': 'UNVERIFIED', 'masked_id': 'GUARDIAN-UNVERIFIED'}), token=token
    )


@auth_bp.route('/approve/<token>/', methods=['GET', 'POST'])
@limiter.limit('30 per minute')
def approve_child(token):
    """Legacy link compatibility without token-only activation.

    Old invitations are routed into the verified parent flow. A leaked or
    replayed UUID can no longer activate a child account by itself.
    """
    return redirect(f'/verify-parent/{token}/', code=303)


@auth_bp.route('/register-parent', methods=['GET', 'POST'])
@auth_bp.route('/register-parent/', methods=['GET', 'POST'])
@limiter.limit('100 per hour')
def register_parent_direct_page():
    if request.method == 'POST':
        try:
            res = begin_parent_registration(request.form)
            session.clear()
            session.permanent = True
            session['pending_parent_user_id'] = res['user_id']
            session['pending_parent_email'] = res['email']
            session['pending_parent_email_verified'] = False
            session['pending_parent_delivery_error'] = not bool(res.get('email_sent'))
            return redirect('/verify-parent-email/')
        except Exception as exc:
            logger.exception("Parent registration failed")
            return render_template('parent_register_direct.html', error="Could not complete parent registration. Please try again."), 400
    return render_template('parent_register_direct.html')


@auth_bp.route('/verify-parent-email/', methods=['GET', 'POST'])
@limiter.limit('30 per minute')
def verify_parent_email_page():
    parent = _pending_parent()
    if not parent:
        return redirect('/register-parent/')
    if session.pop('pending_parent_delivery_error', False):
        if os.getenv('RESEND_API_KEY'):
            delivery_error = 'The account is pending, but Resend could not deliver the OTP. In Resend sandbox mode, register with the account email (littlenet655@gmail.com) or verify your domain in Resend.'
        else:
            delivery_error = 'The account is pending, but the OTP email could not be sent. Check mail configuration, then use Resend.'
    else:
        delivery_error = None
    if request.method == 'POST':
        ok, error, _ = verify_parent_email_otp(parent['user_id'], request.form.get('otp', ''))
        if ok:
            # Email OTP is the final parent activation step: activate the
            # account and sign the parent in. There is no separate
            # selfie/liveness step.
            execute(
                "UPDATE users SET account_status='ACTIVE' WHERE user_id=%s AND role='PARENT' AND account_status='PENDING_APPROVAL'",
                (parent['user_id'],),
            )
            session.pop('pending_parent_user_id', None)
            session.pop('pending_parent_email', None)
            session.pop('pending_parent_email_verified', None)
            session.pop('pending_parent_delivery_error', None)
            active = fetch_one('SELECT * FROM users WHERE user_id=%s', (parent['user_id'],))
            if active and active.get('account_status') == 'ACTIVE':
                _set_session(active)
                try:
                    from services.analytics import capture as analytics_capture
                    analytics_capture(parent['user_id'], 'parent_registered', {})
                except Exception:
                    pass
            return redirect('/parent/dashboard/')
        return render_template('parent_email_verify.html', masked_email=_mask_email(parent['email']), error=error, delivery_error=delivery_error), 400
    return render_template('parent_email_verify.html', masked_email=_mask_email(parent['email']), delivery_error=delivery_error)


@auth_bp.route('/verify-parent-email/resend/', methods=['POST'])
@limiter.limit('5 per 10 minutes')
def resend_parent_email_page():
    parent = _pending_parent()
    if not parent:
        return redirect('/register-parent/')
    ok, error = resend_parent_email_otp(parent['user_id'])
    return render_template('parent_email_verify.html', masked_email=_mask_email(parent['email']), error=error if not ok else None, notice='A new 6-digit code was sent.' if ok else None), (200 if ok else 400)


@auth_bp.route('/register-parent/<token>/', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def register_parent(token):
    return redirect(f'/verify-parent/{token}/')


@auth_bp.route('/logout/',methods=['POST'])
def logout():
    if session.get('usage_session_key'):close_session(session['usage_session_key'])
    session.clear()
    return redirect('/')


@auth_bp.route('/switch-mode/',methods=['POST'])
def switch_mode():
    if session.get('usage_session_key'):close_session(session['usage_session_key'])
    session.clear()
    return redirect('/')


@auth_bp.route('/admin-login/', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def admin_login():
    if request.method == 'POST':
        user = login_user(request.form.get('email', ''), request.form.get('password', ''))
        if not user or user['role'] != 'ADMIN':
            return render_template('login.html', mode='admin', error='Invalid admin credentials'), 401
        _set_session(user)
        return redirect('/admin/')
    return render_template('login.html', mode='admin')


@auth_bp.route('/language/', methods=['POST'])
@login_required
def change_language():
    lang = set_language(session['user_id'], request.form.get('language', 'EN'))
    session['language'] = lang
    return redirect(request.referrer or ('/parent/dashboard/' if session.get('role') == 'PARENT' else '/child/dashboard/'))
