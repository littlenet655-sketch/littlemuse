from flask import Blueprint,render_template,request,redirect,session,jsonify
from extensions import limiter
from decorators import child_required,parent_required
from quiz.service import (
    quizzes,reset,learning_challenges,learning_points,next_feed_quiz,record_feed_answer,
    record_feed_view,feed_quiz_state,required_feed_quiz,complete_required_feed_quiz,
)
from parent.service import owns,children
from database.connection import fetch_one,fetch_all,execute

quiz_bp=Blueprint('quiz',__name__,template_folder='templates')


def _quiz_json(q):
    if not q:return {'available':False}
    return {
        'available':True,
        'required':True,
        'quiz_id':q['quiz_id'],
        'category':q.get('category',''),
        'question':q['question'],
        'options':[q['option_a'],q['option_b'],q['option_c'],q['option_d']],
    }


@quiz_bp.route('/quiz/start/')
@limiter.limit('45 per minute')
@child_required
def start():
    # A latched doom-scroll break is server-owned. Always resume the exact same
    # required question after refresh/new tab instead of creating a new session quiz.
    state=feed_quiz_state(session['user_id'])
    if state['required']:
        q=required_feed_quiz(session['user_id'])
        if not q:return render_template('quiz_result.html',error='Your required age-group quiz is temporarily unavailable. Please retry; the break remains locked.'),503
        qs=[q]
    else:
        qs=quizzes(session['user_id'],2)
    if not qs:return render_template('quiz_result.html',error='No age-group questions available yet.')
    session['quiz_ids']=[q['quiz_id'] for q in qs];session['quiz_index']=0;session['quiz_score']=0
    return render_template('quiz_card.html',quiz=qs[0],question_number=1,total_questions=len(qs))

@quiz_bp.route('/quiz/submit/',methods=['POST'])
@child_required
def submit():
    ids=session.get('quiz_ids') or [];idx=int(session.get('quiz_index',0))
    if idx>=len(ids):return redirect('/quiz/start/')
    expected=ids[idx]
    try:posted=int(request.form.get('quiz_id',0))
    except:return redirect('/quiz/start/')
    if posted!=expected:return ('Invalid quiz state',400)
    # If this is the server-latched brain break, the submitted id must also be
    # the PostgreSQL assignment; session/cookie manipulation cannot swap it.
    state=feed_quiz_state(session['user_id'])
    if state['required']:
        q_required=required_feed_quiz(session['user_id'])
        if not q_required or int(q_required['quiz_id'])!=posted:return ('Invalid required quiz state',409)
    q=fetch_one('SELECT * FROM quizzes WHERE quiz_id=%s',(expected,));ans=request.form.get('answer','');correct=bool(q and ans==q['correct_answer'])
    execute('INSERT INTO child_quiz_attempts(child_id,quiz_id,selected_answer,is_correct) VALUES(%s,%s,%s,%s)',(session['user_id'],expected,ans,correct))
    session['quiz_score']=session.get('quiz_score',0)+(1 if correct else 0);idx+=1;session['quiz_index']=idx
    if idx>=len(ids):
        score=session['quiz_score'];total=len(ids);session.pop('quiz_ids',None);session.pop('quiz_index',None);session.pop('quiz_score',None);reset(session['user_id'])
        return render_template('quiz_result.html',score=score,total=total)
    return render_template('quiz_card.html',quiz=fetch_one('SELECT * FROM quizzes WHERE quiz_id=%s',(ids[idx],)),question_number=idx+1,total_questions=len(ids))

@quiz_bp.route('/quiz/settings/',methods=['GET','POST'])
@parent_required
def settings():
    kids=children(session['user_id']);cid=int(request.values.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    if request.method=='POST':
        try:f=int(request.form.get('quiz_frequency',4))
        except:return ('Invalid frequency',400)
        if not 1<=f<=4:return ('Frequency must be between 1 and 4',400)
        execute('INSERT INTO parent_quiz_settings(parent_id,child_id,quiz_frequency,mandatory_quiz) VALUES(%s,%s,%s,TRUE) ON CONFLICT(child_id) DO UPDATE SET quiz_frequency=EXCLUDED.quiz_frequency,mandatory_quiz=TRUE',(session['user_id'],cid,f))
        return redirect(f'/quiz/settings/?child_id={cid}')
    return render_template('parent_quiz_settings.html',child_id=cid,settings=fetch_one('SELECT * FROM parent_quiz_settings WHERE child_id=%s',(cid,)))

@quiz_bp.route('/parent/quiz-report/')
@parent_required
def report():
    kids=children(session['user_id']);cid=int(request.args.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    rows=fetch_all('SELECT a.*,q.question FROM child_quiz_attempts a JOIN quizzes q ON q.quiz_id=a.quiz_id WHERE a.child_id=%s ORDER BY attempted_at DESC',(cid,))
    return render_template('parent_quiz_report.html',attempts=rows)

@quiz_bp.route('/quiz/save-settings/',methods=['POST'])
@parent_required
def save_settings_alias():return settings()

# ── Server-persistent Feed Quiz API ───────────────────────────────────────────

@quiz_bp.route('/quiz/api/feed-view/',methods=['POST'])
@limiter.limit('120 per minute')
@child_required
def api_feed_view():
    """Record one substantially viewed safe post/reel in PostgreSQL."""
    data=request.get_json(silent=True) or {}
    try:post_id=int(data.get('post_id',0))
    except:return jsonify(error='invalid post_id'),400
    if post_id<=0:return jsonify(error='invalid post_id'),400
    state=record_feed_view(session['user_id'],post_id)
    return jsonify(
        accepted=bool(state.get('accepted')),
        posts_seen=int(state.get('posts_seen') or 0),
        interval=int(state.get('interval') or 4),
        required=bool(state.get('required')),
    )


@quiz_bp.route('/quiz/api/feed-quiz/status/')
@limiter.limit('60 per minute')
@child_required
def api_feed_quiz_status():
    state=feed_quiz_state(session['user_id'])
    return jsonify(
        required=bool(state['required']),
        posts_seen=int(state['posts_seen']),
        interval=int(state['interval']),
        quiz_id=state['quiz_id'],
    )


# Keep the original paths as compatibility aliases, but the browser uses the
# The /quiz/... paths stay exempt from kids-controls gating so the voluntary
# quiz page is always reachable; the periodic latch itself no longer blocks or
# redirects any surface (it is a nudge).
@quiz_bp.route('/api/feed-quiz/')
@quiz_bp.route('/quiz/api/feed-quiz/')
@limiter.limit('45 per minute')
@child_required
def api_feed_quiz():
    """Return the exact server-latched required question."""
    state=feed_quiz_state(session['user_id'])
    if not state['required']:
        return jsonify(available=False,required=False)
    q=required_feed_quiz(session['user_id'])
    if not q:
        return jsonify(available=False,required=True),503
    return jsonify(**_quiz_json(q))


@quiz_bp.route('/api/feed-quiz/answer/',methods=['POST'])
@quiz_bp.route('/quiz/api/feed-quiz/answer/',methods=['POST'])
@limiter.limit('45 per minute')
@child_required
def api_feed_quiz_answer():
    """Submit only the exact PostgreSQL-latched feed quiz, then clear the gate."""
    data=request.get_json(silent=True) or {}
    try: quiz_id = int(data.get('quiz_id',0))
    except: return jsonify(error='invalid quiz_id'),400
    answer = str(data.get('answer','')).strip()
    if not answer: return jsonify(error='answer required'),400
    q=required_feed_quiz(session['user_id'])
    if not q:return jsonify(error='quiz_not_required'),409
    if int(q['quiz_id'])!=quiz_id:return jsonify(error='required_quiz_mismatch'),409

    res = record_feed_answer(session['user_id'], quiz_id, answer)
    is_correct = res[0]
    correct_answer = res[1]
    xp = res[2]
    explanation = res[3] if len(res) > 3 else ""
    if not complete_required_feed_quiz(session['user_id'],quiz_id):
        return jsonify(error='quiz_completion_conflict'),409

    # Streak is a reward/UI detail, not a safety gate, so session storage is fine.
    streak = session.get('quiz_streak', 0)
    if is_correct:
        streak += 1
        bonus_xp = 50 if streak > 0 and streak % 3 == 0 else 0
    else:
        streak = 0
        bonus_xp = 0
    session['quiz_streak'] = streak
    if bonus_xp:
        from database.connection import execute as db_exec
        db_exec(
            '''INSERT INTO child_xp(child_id,xp) VALUES(%s,%s)
               ON CONFLICT(child_id) DO UPDATE SET xp=child_xp.xp+EXCLUDED.xp,updated_at=NOW()''',
            (session['user_id'], bonus_xp)
        )
    return jsonify(
        correct=is_correct,
        correct_answer=correct_answer,
        xp=xp,
        bonus_xp=bonus_xp,
        streak=streak,
        explanation=explanation,
        required=False,
    )

@quiz_bp.route('/api/feed-quiz/explain/<int:quiz_id>/', methods=['POST', 'GET'])
@limiter.limit('45 per minute')
@child_required
def api_feed_quiz_explain(quiz_id):
    """Provides kid-friendly explanation for an incorrect answer."""
    selected = (request.args.get('selected') or (request.get_json(silent=True) or {}).get('selected') or '').strip()
    q = fetch_one('SELECT * FROM quizzes WHERE quiz_id=%s', (quiz_id,))
    if not q:
        return jsonify(error='quiz not found'), 404
    from services.ai import get_ai_client
    client = get_ai_client()
    from quiz.service import age_group
    g = age_group(session['user_id'])
    res = client.explain_quiz_mistake(q['question'], selected or 'Selected option', q['correct_answer'], g)
    return jsonify(
        explanation=res.kid_friendly_explanation,
        encouragement=res.encouragement,
        fun_fact=res.fun_fact
    )

@quiz_bp.route('/learning/')
@child_required
def learning():
    return render_template('learning.html',challenges=learning_challenges(session['user_id']),points=learning_points(session['user_id']))

@quiz_bp.route('/learning/challenge/<int:challenge_id>/',methods=['POST'])
@child_required
def complete_challenge(challenge_id):
    is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
    q=fetch_one('SELECT * FROM learning_challenges WHERE challenge_id=%s AND active=TRUE',(challenge_id,))
    if not q:
        return (jsonify(error='Challenge not found'), 404) if is_ajax else ('Challenge not found',404)
    allowed={x['challenge_id'] for x in learning_challenges(session['user_id'])}
    if challenge_id not in allowed:
        return (jsonify(error='Challenge not available for this age group'), 403) if is_ajax else ('Challenge not available for this age group',403)
    data = request.get_json(silent=True) or request.form
    response=(data.get('response') or '').strip();expected=(q.get('expected_answer') or '').strip()
    correct=True if not expected else response.casefold()==expected.casefold()
    points=q['points'] if correct else 0
    if correct:
        execute('''INSERT INTO learning_challenge_attempts(child_id,challenge_id,response,completed,points_awarded)
          VALUES(%s,%s,%s,TRUE,%s)
          ON CONFLICT(child_id,challenge_id) DO UPDATE SET response=EXCLUDED.response,completed=TRUE,points_awarded=EXCLUDED.points_awarded,completed_at=NOW()''',
          (session['user_id'],challenge_id,response,points))
    else:
        execute('''INSERT INTO learning_challenge_attempts(child_id,challenge_id,response,completed,points_awarded)
          VALUES(%s,%s,%s,FALSE,0)
          ON CONFLICT(child_id,challenge_id) DO UPDATE SET response=EXCLUDED.response,completed=FALSE,points_awarded=0,completed_at=NOW()''',
          (session['user_id'],challenge_id,response))
    new_total = learning_points(session['user_id'])
    if is_ajax:
        return jsonify({
            'ok': True,
            'correct': correct,
            'points_awarded': points,
            'new_total_points': new_total,
            'challenge_id': challenge_id,
            'title': q['title'],
            'message': f"Well done! You earned +{points} pts!" if correct else "Incorrect answer. Check the prompt and try again!"
        })
    return redirect('/learning/')

@quiz_bp.route('/parent/learning-report/')
@parent_required
def learning_report():
    kids=children(session['user_id']);cid=int(request.args.get('child_id') or (kids[0]['user_id'] if kids else 0))
    if not owns(session['user_id'],cid):return ('Forbidden',403)
    rows=fetch_all('''SELECT a.*,c.title,c.challenge_type,c.points FROM learning_challenge_attempts a
      JOIN learning_challenges c ON c.challenge_id=a.challenge_id WHERE a.child_id=%s ORDER BY a.completed_at DESC''',(cid,))
    child=fetch_one('SELECT full_name FROM users WHERE user_id=%s',(cid,)) or {'full_name':'Child'}
    return render_template('parent_learning_report.html',rows=rows,child=child,child_id=cid)
