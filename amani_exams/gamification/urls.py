from django.urls import path

from . import views

urlpatterns = [
    # student: home, cabinet, ledger, profile, leaderboard
    path("gamification/me/", views.my_summary),
    path("gamification/ack/", views.acknowledge),
    path("gamification/badges/", views.my_badges),
    path("gamification/xp/", views.my_xp),
    path("gamification/profile/", views.my_profile),
    path("gamification/leaderboard/", views.leaderboard),
    path("gamification/catalog/", views.badge_catalog),
    # review mode progress (Mistake Master)
    path("results/<int:attempt_id>/review/seen/", views.review_seen),
    # practice mode
    path("practice/subjects/", views.practice_subjects),
    path("practice/start/", views.practice_start),
    path("practice/<int:session_id>/", views.practice_current),
    path("practice/<int:session_id>/answer/", views.practice_answer),
    # staff
    path("practice/subjects/<int:subject_id>/toggle/", views.practice_toggle_subject),
    path("practice/mark-eligible/", views.practice_mark_eligible),
    # admin
    path("gamification/settings/", views.gamification_settings),
]
