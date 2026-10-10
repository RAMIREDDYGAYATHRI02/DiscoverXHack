from django.urls import path

from . import views

urlpatterns = [
    path("state", views.state_view, name="state"),
    path("staff", views.staff_view, name="staff"),
    path("shifts", views.shifts_view, name="shifts"),
    path("listings", views.listings_view, name="listings"),
    path("listings/<str:listing_id>/withdraw", views.listing_transition("WITHDRAW"), name="withdraw-listing"),
    path("listings/<str:listing_id>/claim", views.listing_transition("CLAIM"), name="claim-listing"),
    path("listings/<str:listing_id>/unclaim", views.listing_transition("UNCLAIM"), name="unclaim-listing"),
    path("listings/<str:listing_id>/approve", views.listing_transition("APPROVE"), name="approve-listing"),
    path("listings/<str:listing_id>/reject", views.listing_transition("REJECT"), name="reject-listing"),
    path("history", views.history_view, name="history"),
    path("actions", views.action_view, name="actions"),
]
