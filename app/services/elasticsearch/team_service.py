from app.services.elasticsearch.connection import get_elasticsearch_connection
from elasticsearch import NotFoundError
from uuid import UUID

es = get_elasticsearch_connection()
INDEX_NAME = "teams"

def serialize_team(team):
    return {
        "team_id": str(team.team_id),
        "name": team.name,
        "description": team.description or "",
        "contact_email": team.contact_email or "",
        "slack_channel": team.slack_channel or "",
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "updated_at": team.updated_at.isoformat() if team.updated_at else None,
        "deleted_at": team.deleted_at.isoformat() if team.deleted_at else None,
    }

def index_team(team):
    try:
        doc = serialize_team(team)
        es.index(index=INDEX_NAME, id=str(team.team_id), body=doc, refresh=True)
        print(f"✅ Team {team.team_id} indexed")
    except Exception as e:
        print(f"❌ Error indexing team {team.team_id}: {e}")

def get_team_from_es(team_id: UUID):
    try:
        result = es.get(index=INDEX_NAME, id=str(team_id))
        return result["_source"]
    except NotFoundError:
        return None
    except Exception as e:
        print(f"[ES] Get team error: {str(e)}")
        return None

def get_all_teams_from_es():
    try:
        result = es.search(index=INDEX_NAME, body={"query": {"match_all": {}}}, size=1000)
        return [hit["_source"] for hit in result["hits"]["hits"]]
    except Exception as e:
        print(f"[ES] Search teams error: {str(e)}")
        return []
