from django.urls import path

from . import views

urlpatterns = [
    path('<str:app_label>/<str:model_name>/', views.BulkListEditView.as_view(), name='bulk_list_edit'),
]
