# accounts/views.py
from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import RegisterForm
from django.shortcuts import render
from django.contrib.auth.decorators import user_passes_test
from django.utils import timezone
from .models import RegistrationToken

class RegisterView(View):
    template_name = "accounts/register.html"

    def get(self, request):
        token_value = request.GET.get("token")
        if not token_value:
            messages.error(request, "Registration link missing or invalid.")
            return redirect("login")

        try:
            token = RegistrationToken.objects.get(token=token_value)
        except RegistrationToken.DoesNotExist:
            messages.error(request, "Invalid registration link.")
            return redirect("login")

        if not token.is_valid():
            messages.error(request, "This registration link has expired or was already used.")
            return redirect("login")

        form = RegisterForm()
        return render(request, self.template_name, {'form': form, 'token': token_value})

    def post(self, request):
        token_value = request.POST.get("token")
        try:
            token = RegistrationToken.objects.get(token=token_value)
        except RegistrationToken.DoesNotExist:
            messages.error(request, "Invalid or expired registration link.")
            return redirect("login")

        if not token.is_valid():
            messages.error(request, "This registration link has expired or was already used.")
            return redirect("login")

        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            token.used = True
            token.save()
            messages.success(request, "Registration successful! Please log in.")
            return redirect('login')

        return render(request, self.template_name, {'form': form, 'token': token_value})



