import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from sync.views import jwt_required
from sync.sql_helper import get_connection, release_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

EGATE_FLAG = "##EGATE##"


@csrf_exempt
@jwt_required
@require_http_methods(["POST"])
def e_gate_billing(request):
    """
    Mark an acc_invmast invoice as E-Gated.

    Request body (single field):
        {"billno": "A-1"}

    where:
        "A"   -> type  (character part)
        "1"   -> billno (numeric part, must be > 0)

    On success the '##EGATE##' flag is appended to the matching row's ft column.
    If '##EGATE##' already appears anywhere in ft, responds "Already billed".
    """
    try:
        payload = json.loads(request.body or b"{}")
    except Exception:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    value = (payload.get("billno") or "").strip()
    if not value:
        return JsonResponse({"detail": "billno is required, e.g. A-1"}, status=400)

    if "-" not in value:
        return JsonResponse(
            {"detail": "Invalid billno format, expected like 'A-1'"},
            status=400,
        )

    type_part, num_part = value.rsplit("-", 1)
    type_part = type_part.strip()
    num_part = num_part.strip()

    if not type_part:
        return JsonResponse(
            {"detail": "Invalid billno: type part is empty, expected like 'A-1'"},
            status=400,
        )

    try:
        billno = int(num_part)
    except ValueError:
        return JsonResponse(
            {"detail": f"Invalid billno: '{num_part}' is not a valid number"},
            status=400,
        )

    if billno <= 0:
        return JsonResponse(
            {"detail": "Invalid billno: must be greater than 0"},
            status=400,
        )

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT billno, ft FROM DBA.acc_invmast WHERE TRIM(type) = ? AND billno = ?",
            (type_part, billno),
        )
        row = cur.fetchone()

        if not row:
            return JsonResponse({"detail": "No matching invoice found"}, status=404)

        current_ft = (row[1] or "").strip()

        if EGATE_FLAG in current_ft:
            return JsonResponse(
                {
                    "status": "already_billed",
                    "detail": "Already billed",
                    "type": type_part,
                    "billno": billno,
                    "ft": current_ft,
                },
                status=400,
            )

        new_ft = EGATE_FLAG if not current_ft else current_ft + EGATE_FLAG

        cur.execute(
            "UPDATE DBA.acc_invmast SET ft = ? WHERE TRIM(type) = ? AND billno = ?",
            (new_ft, type_part, billno),
        )

        logging.info("✅ E-Gate billed: type=%s billno=%s", type_part, billno)
        return JsonResponse(
            {
                "status": "success",
                "detail": "E-Gate billed successfully",
                "type": type_part,
                "billno": billno,
                "ft": new_ft,
            }
        )
    except Exception as e:
        logging.error("❌ E-Gate billing failed: %s", e)
        return JsonResponse({"detail": f"Failed: {e}"}, status=500)
    finally:
        try:
            cur.close()
            release_connection(conn)
        except Exception:
            pass