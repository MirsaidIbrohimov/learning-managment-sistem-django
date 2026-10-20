from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.functions import Coalesce

from .models import Post, PostComment, PostLike


def published_posts_with_counts():
    # Independent indexed subqueries avoid likes x comments Cartesian products.
    def count_for(model):
        rows = model.objects.filter(post_id=OuterRef('pk')).order_by().values('post_id')
        return Coalesce(Subquery(rows.annotate(total=Count('pk')).values('total'),
                                 output_field=IntegerField()), 0)
    return Post.objects.filter(is_published=True).select_related('author').annotate(
        list_likes_count=count_for(PostLike), list_comments_count=count_for(PostComment),
    )
