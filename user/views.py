from itertools import groupby
from typing import Any

from django.contrib import auth
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import Avg
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.generic import ListView, View

from manager.models import Study

from .forms import SignupForm
from .models import Profile, Review


def write_review(request, pk):
    if request.method == "POST":
        reviewer = request.user
        reviewee = User.objects.get(pk=pk)
        study_id = request.POST["study"]
        content = request.POST["review"]
        score = request.POST["score"]
        study = Study.objects.get(pk=study_id)
        if reviewer == reviewee:
            raise Http404("same user")
        if not {reviewer, reviewee}.issubset(set(study.members.all())):
            raise Http404("not member")
        review, created = Review.objects.get_or_create(
            study=study,
            reviewer=reviewer,
            reviewee=reviewee,
            defaults={"score": score, "review": content},
        )
        if not created:
            review.score = score
            review.review = content
        review.save()
        return redirect("manager:study_detail", study_id)
    else:
        raise Http404("잘못된 접근입니다.")


def logout(request):
    auth.logout(request)
    return redirect("recruits:index")


class LoginView(View):
    template_name = "users/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("recruits:index")
        form = AuthenticationForm(request=request)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth.login(request, user)
            return redirect("recruits:index")

        return render(request, self.template_name, {"form": form})


class SignupView(View):
    template_name = "users/signup.html"

    def get(self, request):
        form = SignupForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = SignupForm(data=request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password_check"]
            nickname = form.cleaned_data["nickname"]
            user = User.objects.create_user(username=username, password=password)
            Profile.objects.create(user=user, nickname=nickname)
            return redirect("users:login")

        return render(request, self.template_name, {"form": form})


class MyHistoryView(ListView):
    model = Study
    template_name = "users/info.html"
    context_object_name = "studies"
    paginate_by = 3

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        reviews_for_studies_on_current_page = Review.objects.filter(
            reviewer=self.request.user,
            study__in=context["studies"],
        ).order_by("study")

        grouped_reviews = [
            (study, list(reviews))
            for study, reviews in groupby(
                reviews_for_studies_on_current_page, key=lambda review: review.study
            )
        ]

        context["grouped_reviews"] = grouped_reviews
        context["my_study"] = Study.objects.filter(members=self.request.user)
        context["nickname"] = Profile.objects.get(user=self.request.user).nickname
        avg_score_info = Review.objects.filter(reviewee=self.request.user).aggregate(
            avg_score=Avg("score")
        )
        context["avg_score"] = avg_score_info["avg_score"]
        page = context["page_obj"]
        paginator = page.paginator
        pagelist = paginator.get_elided_page_range(
            page.number, on_each_side=3, on_ends=0
        )
        context["pagelist"] = pagelist
        return context

    def get_queryset(self):
        return Study.objects.filter(
            members=self.request.user,
            reviews__reviewer=self.request.user,
        ).distinct()

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_authenticated:
            return super().get(request, *args, **kwargs)
        return redirect("users:login")


class UserSocialSignupView(View):
    def get(self, request):
        profile = Profile.objects.filter(user=request.user)
        if not profile:
            return render(request, "users/social_signup.html")
        else:
            return redirect("recruits:index")

    def post(self, request):
        nickname = request.POST["nickname"]
        if Profile.objects.filter(nickname=nickname).exists():
            return render(
                request,
                "users/social_signup.html",
                {"error": "nickname is already exists"},
            )
        else:
            Profile.objects.create(user=request.user, nickname=nickname)
            return redirect("users:social_signup")
