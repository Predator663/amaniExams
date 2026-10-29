from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.notification_list),
    path("notifications/read/", views.notifications_read),
    path("push/public-key/", views.push_public_key),
    path("push/subscribe/", views.push_subscribe),
    path("push/unsubscribe/", views.push_unsubscribe),
    path("announcements/", views.announcements),
    path("messages/", views.my_messages),
    path("messages/<int:message_id>/dismiss/", views.dismiss_message),
    path("admin/messages/", views.admin_messages),
    path("admin/messages/<int:message_id>/", views.admin_message_delete),
]
