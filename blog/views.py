from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse
from django.core.paginator import Paginator
from .models import Post, PostComment, PostLike, CommentLike
from .forms import PostForm, CommentForm
from .querysets import published_posts_with_counts
from coin.models import ActivityLog
from telegram_bot.utils import notify_group, notify_user

def post_list(request):
    search_query = request.GET.get('q')
    filter_type = request.GET.get('type')
    
    posts_qs = published_posts_with_counts()
    
    if search_query:
        posts_qs = posts_qs.filter(
            Q(title__icontains=search_query) | 
            Q(content__icontains=search_query)
        )
    
    if filter_type:
        posts_qs = posts_qs.filter(post_type=filter_type)
    
    # Deterministic ordering keeps pagination stable for search crawlers.
    paginator = Paginator(posts_qs.order_by('-created_at', '-pk'), 6)
    page_number = request.GET.get('page')
    posts = paginator.get_page(page_number)
    
    return render(request, 'blog/post_list.html', {
        'posts': posts, 
        'search_query': search_query, 
        'filter_type': filter_type
    })

def post_detail(request, pk):
    post = get_object_or_404(Post.objects.select_related('author'), pk=pk, is_published=True)
    comments = post.comments.select_related('user').all()
    is_liked = request.user.is_authenticated and post.likes.filter(user=request.user).exists()
    liked_comment_ids = (
        list(CommentLike.objects.filter(
            user=request.user,
            comment__in=comments,
        ).values_list('comment_id', flat=True))
        if request.user.is_authenticated else []
    )
    
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url='login')
        form = CommentForm(request.POST)
        if form.is_valid():
            # 1 soatda 1 ta izoh çeklovi
            from datetime import timedelta
            from django.utils import timezone
            one_hour_ago = timezone.now() - timedelta(hours=1)
            recent_comment = PostComment.objects.filter(
                user=request.user,
                created_at__gte=one_hour_ago
            ).exists()
            
            if recent_comment:
                messages.warning(request, "Siz 1 soatda faqat 1 ta izoh yozişingiz mumkin. Keyinroq urinib köring.")
                return redirect('blog:post_detail', pk=pk)
            
            comment = form.save(commit=False)
            comment.post = post
            comment.user = request.user
            comment.save()
            
            if request.user.is_premium:
                request.user.add_coins(1, f"Postga izoh (Premium): {post.title}")
                messages.success(request, "Izoh qoldirildi (+1 coin Premium bonus)! ✨")
            else:
                request.user.remove_coins(1, f"Postga izoh yoziş: {post.title}")
                messages.success(request, "Izoh qoldirildi (-1 coin)")
            ActivityLog.objects.create(
                user=request.user,
                action_type='comment_post',
                description=f"Postga izoh qoldirdi: {post.title}"
            )
            return redirect('blog:post_detail', pk=pk)
    else:
        form = CommentForm()
        
    return render(request, 'blog/post_detail.html', {
        'post': post,
        'comments': comments,
        'is_liked': is_liked,
        'liked_comment_ids': liked_comment_ids,
        'form': form
    })

@login_required
def post_create(request):
    if not (request.user.is_teacher or request.user.is_admin):
        messages.error(request, "Faqat öqituvçilar va adminlar post qöşişi mumkin!")
        return redirect('blog:post_list')
        
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()

            type_name = dict(Post.POST_TYPES).get(post.post_type, post.post_type)
            post_url = request.build_absolute_uri(reverse('blog:post_detail', args=[post.pk]))

            import threading

            post_title = post.title
            author_name = post.author.full_name
            content_preview = post.content[:200] + ('...' if len(post.content) > 200 else '')
            author_pk = request.user.pk

            def _send_post_notifications():
                from django.db import connection
                connection.close()
                try:
                    notify_group(
                        f"📰 <b>Yangi post!</b>\n\n"
                        f"📌 <b>{post_title}</b>\n"
                        f"📂 Turi: {type_name}\n"
                        f"✍️ Muallif: {author_name}\n\n"
                        f"📖 {content_preview}\n\n"
                        f"🔗 <a href=\"{post_url}\">Saytda töliq öqing!</a>"
                    )
                    from accounts.models import CustomUser
                    users = CustomUser.objects.filter(
                        telegram_id__isnull=False
                    ).exclude(telegram_id='').exclude(pk=author_pk)
                    for u in users:
                        notify_user(
                            u.telegram_id,
                            f"📰 <b>Yangi post çiqdi!</b>\n\n"
                            f"📌 <b>{post_title}</b>\n"
                            f"📂 {type_name}\n"
                            f"✍️ {author_name}\n\n"
                            f"🔗 <a href=\"{post_url}\">Saytda töliq öqing!</a>"
                        )
                except Exception as e:
                    print(f"Post notification xatolik: {e}")

            threading.Thread(target=_send_post_notifications, daemon=True).start()

            messages.success(request, "Post muvaffaqiyatli yaratildi!")
            return redirect('blog:post_list')
    else:
        form = PostForm()
        
    return render(request, 'blog/post_form.html', {'form': form})

@login_required
def toggle_like(request, pk):
    post = get_object_or_404(Post, pk=pk)
    like = PostLike.objects.filter(post=post, user=request.user).first()
    
    if like:
        coin_back = 2 if request.user.is_premium else 1
        if like.coin_awarded:
            request.user.remove_coins(coin_back, f"Postga like olib taşlandi: {post.title}")
            messages.info(request, f"Like olib taşlandi (-{coin_back} coin)")
        like.delete()
    else:
        coin_amount = 2 if request.user.is_premium else 1
        like = PostLike.objects.create(post=post, user=request.user, coin_awarded=True)
        request.user.add_coins(coin_amount, f"Postga like bosildi: {post.title}")
        ActivityLog.objects.create(
            user=request.user,
            action_type='like_post',
            description=f"Postga like bosdi: {post.title} (+{coin_amount} coin)"
        )
        messages.success(request, f"Like bosildi (+{coin_amount} coin)")
        
    return redirect('blog:post_detail', pk=pk)


@login_required
def admin_posts(request):
    if not (request.user.is_teacher or request.user.is_admin):
        messages.error(request, "Bu sahifaga kiriş huquqingiz yöq!")
        return redirect('blog:post_list')
    
    posts = Post.objects.all()
    
    if request.user.is_teacher and not request.user.is_admin:
        posts = posts.filter(author=request.user)
    
    post_type = request.GET.get('type')
    if post_type:
        posts = posts.filter(post_type=post_type)
    
    search = request.GET.get('q')
    if search:
        posts = posts.filter(Q(title__icontains=search) | Q(content__icontains=search))
    
    return render(request, 'blog/admin_posts.html', {
        'posts': posts.order_by('-created_at'),
        'post_types': Post.POST_TYPES,
    })


@login_required
def post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    
    if not request.user.is_admin and post.author != request.user:
        messages.error(request, "Bu postni tahrirlaş huquqingiz yöq!")
        return redirect('blog:post_list')
    
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, "Post muvaffaqiyatli yangilandi!")
            return redirect('blog:admin_posts')
    else:
        form = PostForm(instance=post)
    
    return render(request, 'blog/post_form.html', {'form': form, 'post': post, 'edit_mode': True})


@login_required
def post_delete(request, pk):
    post = get_object_or_404(Post, pk=pk)
    
    if not request.user.is_admin and post.author != request.user:
        messages.error(request, "Bu postni öçiriş huquqingiz yöq!")
        return redirect('blog:post_list')
    
    if request.method == 'POST':
        post.delete()
        messages.success(request, "Post öçirildi!")
        return redirect('blog:admin_posts')
    
    return render(request, 'blog/post_delete.html', {'post': post})


@login_required
def toggle_comment_like(request, pk):
    comment = get_object_or_404(PostComment, pk=pk)
    like = CommentLike.objects.filter(comment=comment, user=request.user).first()
    
    if like:
        coin_back = 2 if request.user.is_premium else 1
        like.delete()
        comment.user.remove_coins(coin_back, f"Izohga like olib taşlandi")
        messages.info(request, f"Like olib taşlandi (-{coin_back} coin izoh egasidan)")
    else:
        coin_amount = 2 if request.user.is_premium else 1
        CommentLike.objects.create(comment=comment, user=request.user)
        comment.user.add_coins(coin_amount, f"Izohga like olindi")
        ActivityLog.objects.create(
            user=comment.user,
            action_type='comment_liked',
            description=f"Izohga like olindi: {comment.content[:30]} (+{coin_amount} coin)"
        )
        messages.success(request, f"Like bosildi (+{coin_amount} coin izoh egasiga)")
    
    return redirect('blog:post_detail', pk=comment.post.pk)
