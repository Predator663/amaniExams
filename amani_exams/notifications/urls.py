from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.notification_list),
    path("notifications/read/", views.notifications_read),
    path("push/public-key/", views.push_public_key),
    path("push/subscribe/", views.push_subscribe),
    path("push/unsubscribe/", views.push_unsubscribe),
    path("announcements/", views.announcements),
]
