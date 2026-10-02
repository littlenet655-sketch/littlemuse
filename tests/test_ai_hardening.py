import time
import pytest
from safety.common import ModelTimeout,normalize_signals,timed_call
from safety.policy import decide

def test_signal_contract_is_complete_and_max_preserving():
    s=normalize_signals({'sexual_score':.62,'general_score':.1,'errors':'x'},category='IMAGE')
    for key in ['adult_score','sexual_score','violence_score','weapon_score','toxicity_score','general_score','category','total_safety_failure','partial_safety_failure','errors']:
        assert key in s
    assert s['adult_score']==.62 and s['general_score']>=.62 and s['errors']==['x']

def test_timed_call_returns_without_waiting_forever():
    start=time.monotonic()
    with pytest.raises(ModelTimeout):timed_call('test',lambda:time.sleep(.2),.02)
    assert time.monotonic()-start<.15

def test_max_ensemble_adult_and_weapon_never_average_down():
    assert decide({'adult_score':.41,'sexual_score':.05,'general_score':.01},'STANDARD').action=='BLOCK'
    assert decide({'weapon_score':.46,'general_score':.01},'STANDARD').action=='BLOCK'

def test_enabled_optional_failure_is_not_silent_allow():
    assert decide({'partial_safety_failure':True,'general_score':.01},'STRICT').action=='REVIEW'
    assert decide({'total_safety_failure':True},'STRICT').action=='BLOCK'
