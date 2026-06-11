import sys
sys.path.insert(0, '/app')
from db.models import get_session, RescueDraft, RescuePost, RescueAnalysis, HitlReview, ChannelSend

s = get_session()
s.query(ChannelSend).delete()
s.query(HitlReview).delete()
s.query(RescueDraft).delete()
s.query(RescueAnalysis).delete()
s.query(RescuePost).delete()
s.commit()
print('DB cleared')
