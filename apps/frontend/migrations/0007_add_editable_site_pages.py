from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('frontend', '0006_seed_metric_catalog')]

    operations = [
        migrations.CreateModel(
            name='SitePage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('path', models.CharField(help_text='Public path, for example / or /rooms/.', max_length=180, unique=True)),
                ('navigation_title', models.CharField(max_length=80)),
                ('browser_title', models.CharField(max_length=160)),
                ('meta_description', models.CharField(max_length=300)),
                ('hero_eyebrow', models.CharField(blank=True, max_length=100)),
                ('hero_title', models.CharField(blank=True, max_length=180)),
                ('hero_summary', models.TextField(blank=True)),
                ('is_published', models.BooleanField(default=False)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['path']},
        ),
    ]
