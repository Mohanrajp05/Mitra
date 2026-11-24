

from app.core.security import get_current_user
from app.database.connection import close_pool, get_connection, open_pool
from app.main import app
from fastapi.testclient import TestClient


def main() -> None:
    try:
        open_pool()
    except Exception as exc:
        print(f"DATABASE_UNAVAILABLE: {type(exc).__name__}")
        return

    candidate_id = None
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, owner_user_id FROM candidates LIMIT 1")
                row = cursor.fetchone()

        if row is None:
            print("NO_CANDIDATES: nothing to verify")
            return

        candidate_id = str(row["id"])
        owner_user_id = str(row["owner_user_id"])

        app.dependency_overrides[get_current_user] = lambda: {
            "id": owner_user_id,
            "email": "audit@example.com",
            "user_metadata": {},
        }

        with TestClient(app) as client:
            base = f"/api/candidates/{candidate_id}/consent"

            initial = client.get(base)
            granted = client.put(
                base,
                json={"consent_type": "resume_processing", "granted": True},
            )
            granted_body = granted.json()
            withdrawn = client.put(
                base,
                json={"consent_type": "resume_processing", "granted": False},
            )
            withdrawn_body = withdrawn.json()

            print(f"initial_status_code: {initial.status_code}")
            print(f"initial_status: {initial.json().get('status')}")
            print(f"grant_status_code: {granted.status_code}")
            print(f"granted_status: {granted_body.get('status')}")
            print(f"granted_has_decided_at: {bool(granted_body.get('decided_at'))}")
            print(f"withdraw_status_code: {withdrawn.status_code}")
            print(f"withdrawn_status: {withdrawn_body.get('status')}")
    finally:
        app.dependency_overrides.clear()
        if candidate_id:
            try:
                open_pool()
                with get_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM candidate_consents WHERE candidate_id = %s",
                            (candidate_id,),
                        )
                print("cleanup: consent rows removed")
            except Exception as exc:
                print(f"CLEANUP_FAILED: {type(exc).__name__}")
        try:
            close_pool()
        except Exception:
            pass


if __name__ == "__main__":
    main()
