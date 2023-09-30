from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy, reverse
from django.shortcuts import render, redirect

from django.contrib.auth.models import User
from common.utils import s3_file_upload
from recruit.models import Recruit
from .models import File, Post, Study, Task
from .forms import FileFormSet, PostCreateForm, StudyForm


class StudyView(LoginRequiredMixin, ListView):
    model = Study
    template_name = "studies/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["my_studies"] = Study.objects.filter(
            creator=self.request.user, is_active=True
        )
        context["in_studies"] = Study.objects.filter(
            members=self.request.user, is_active=True
        ).exclude(creator=self.request.user)
        context["my_recruits"] = Recruit.objects.filter(creator=self.request.user)
        context["like_recruits"] = Recruit.objects.filter(like_users=self.request.user)
        return context


class StudyDetailView(LoginRequiredMixin, DetailView):
    model = Study
    template_name = "studies/detail.html"
    context_object_name = "study"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tasks"] = Task.objects.filter(study=self.object)
        return context


class StudyDoneView(LoginRequiredMixin, View):
    def post(self, request, pk):
        study = get_object_or_404(Study, id=pk)
        study.status = 4
        study.save()
        return redirect("manager:studies_list")


class StudyFinishView(LoginRequiredMixin, View):
    def post(self, request, pk):
        study = get_object_or_404(Study, id=pk)
        study.status = 3
        study.save()
        return redirect("manager:studies_list")


class StudyLeaveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        study = get_object_or_404(Study, id=pk)
        study.members.remove(request.user)
        study.save()
        return redirect("manager:studies_list")


class StudyKickoutView(LoginRequiredMixin, View):
    def post(self, request, study_id, member_id):
        user = get_object_or_404(User, id=member_id)
        study = get_object_or_404(Study, id=study_id)
        study.members.remove(user)
        study.save()
        return redirect("manager:study_detail", study_id)


class StudyModifyView(LoginRequiredMixin, UpdateView):
    model = Study
    form_class = StudyForm
    template_name = "studies/modify.html"
    success_url = reverse_lazy("manager:study_detail")

    def get_success_url(self):
        return reverse("manager:study_detail", kwargs={"pk": self.object.id})


class PostView(LoginRequiredMixin, ListView):
    model = Post
    template_name = "studies/tasks/board.html"
    context_object_name = "posts"

    def get_queryset(self):
        task_id = self.kwargs["pk"]
        queryset = Post.objects.filter(task_id=task_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["task"] = get_object_or_404(Task, id=self.kwargs["pk"])
        return context


class PostDetailView(LoginRequiredMixin, DetailView):
    model = Post
    template_name = "studies/tasks/posts/detail.html"
    context_object_name = "post"


@login_required
def create_post_with_files(request, pk):
    template_name = "studies/tasks/posts/create.html"

    if request.method == "POST":
        post_form = PostCreateForm(request.POST)
        file_formset = FileFormSet(request.POST, request.FILES)

        if post_form.is_valid() and file_formset.is_valid():
            post_data = post_form.cleaned_data
            post = Post.objects.create(
                title=post_data["title"],
                task_id=pk,
                author=request.user,
                content=post_data["content"],
            )

            for file in file_formset.files.values():
                url = s3_file_upload(file, "files")
                instance = File.objects.create(url=url)
                post.files.add(instance)

            post_list_url = reverse("manager:post_list", kwargs={"pk": pk})

            return redirect(post_list_url)
        else:
            for form in file_formset:
                print(f"form.errors:{form.errors}")

    else:
        post_form = PostCreateForm()
        file_formset = FileFormSet(queryset=File.objects.none())

    context = {"post_form": post_form, "file_formset": file_formset, "pk": pk}

    return render(request, template_name, context)
