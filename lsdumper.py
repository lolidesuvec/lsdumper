#!/usr/bin/env python3
import re, sys, os, json, time, shutil, datetime, gc, requests
from vk_api import VkApi, audio
from vk_api.exceptions import AuthError, VkApiError
from PIL import Image
page_number = 5

prev_id = prev_date = offset_count = progress_left = const_offset_count = 0

dump_audiomessages = True
dump_photos = True
dump_graffiti = True
dump_stickers = True
dump_docs = True
dump_json = True

def write(dir, bin):
    with open(dir, 'a') as file:
        file.write(bin + '\n')

def log(status, string, end_symbol='\n'):
    if status == 0: prefix = '\33[90m' # info
    if status == 1: prefix = '\033[31;1m' # error
    if status == 2: prefix = '\033[33;1m' # warn
    if status == 3: prefix = '\033[32;1m' # pass
    print(prefix + f'[{datetime.datetime.now().strftime("%H:%M:%S")}]\033[0m {string}', end=end_symbol)

def sizeof_fmt(num):
    for x in ['bytes', 'KB', 'MB', 'GB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0
    return "%3.1f %s" % (num, 'TB')

def fix_val(number, digits):
    return f'{number:.{digits}f}'

def str_to_plus(string):
    return str(abs(int(string)))

def str_to_minus(string):
    return str(-abs(int(string)))

def str_fix(string):
    return string.translate(str.maketrans('', '', '\\/?|*<>:."'))

def str_cut(string, letters, postfix='...'):
    return string[:letters] + (string[letters:] and postfix)

def str_esc(string, url_parse=False):
    replaced = []
    url_regex = r"[-a-zA-Zа-яА-Я0-9@:%_\+.~#?&//=]{2,256}\.[a-zA-Zа-яА-Я0-9]{2,4}\b(\/[-a-zA-Zа-яА-Я0-9@:%_\+.~#?&//=]*)?"
    html_escape_table = {"&": "&amp;", '"': "&quot;", "'": "&apos;", ">": "&gt;", "<": "&lt;", "\n": "<br/>\n" if url_parse == True else "\n"}
    string = "".join(html_escape_table.get(c, c) for c in string)
    link_matches = re.finditer(url_regex, string)#, re.MULTILINE)
    for matchNum, match in enumerate(link_matches, start=1):
        if url_parse and match.group()[:+4] in ['http', 'vk.co'] and match.group() not in replaced:
            string = string.replace(match.group(), f'<a href="{match.group()}" title="{match.group()}">{str_cut(match.group(), 50)}</a>')
            replaced.append(match.group())
    return string

def rqst_method(method, values={}):
    while True:
        try:
            request = vk.method(method, values, raw=True)
            return request['response']
        except Exception as ex:
            if str(ex).startswith('[5] User authorization failed: '):
                log(1, 'autechre error: ' + str(ex)[31:])
                sys.exit()
            if str(ex).endswith('Invalid user id') or str(ex).endswith('group_ids is undefined'):
                return None
            if str(ex).endswith('Internal server error'):
                log(2, f'internal catched, waiting...   ')
                time.sleep(60)
            else:
                log(2, f'execption in \'{method}\': {str(ex)}   ')
                time.sleep(5)

def rqst_file(url, dir):
    if not os.path.exists(dir):
        while True:
            try:
                with requests.get(url, stream=True) as request:
                    if request.status_code not in [403, 404, 504]:
                        with open(dir, 'wb') as file:
                            shutil.copyfileobj(request.raw, file)
                    else:
                        log(1, f'{os.path.basename(dir)} not saved ({request.status_code})    ')
                break
            except Exception:# as ex:
                #`log(2, f'execption in \'{os.path.basename(dir)}\': {str(ex)}   ')
                time.sleep(5)
                
def rqst_dialogs():
    conversations = []
    count = rqst_method('messages.getConversations', {'count': 0})['count']
    for offset in range(count // 200 + 1):
        chunk = rqst_method('messages.getConversations', {'count': 200, 'extended': 1, 'offset': offset * 200})
        for item in chunk['items']:
            conversations.append(item['conversation']['peer']['id'])
    log(0, 'loaded %s dialogs!' % len(conversations))
    return conversations

def rqst_user(user_id, save=True):
    for i in range(len(users)):
        if users[i]['id'] == user_id:
            return users[i]

    if user_id > 0:
        object = rqst_method('users.get', {'user_ids': user_id, 'fields': 'photo_200'})[0]
        object = {'id': user_id, 'photo': object['photo_200'], 'name': object['first_name'] + ' ' + object['last_name']}
    else:
        object = rqst_method('groups.getById', {'group_id': str_to_plus(user_id), 'fields': 'photo_200'})[0]
        object = {'id': user_id, 'photo': object['photo_200'], 'name': object['name']}

    if save:
        rqst_file(object['photo'], f'userpics/id{user_id}.jpg')
        users[len(users)] = object
        
    return object

def rqst_thumb(input, th_w, th_h):
    try:
        image = Image.open(input).convert('RGB')
    except Exception as ex:
        log(1, os.path.basename(input) + f' is broken: {str(ex)}    ')
        return {'path': 'broken', 'height': 100, 'width': 100}
    
    src_w, src_h = image.size
    if src_w > th_w or src_h > th_h:
        path = 'photos/thumbnails/th_' + os.path.basename(input)
        image.thumbnail((th_w, th_h))
        src_w, src_h = image.size
        image.save(path)
    else:
        path = 'photos/' + os.path.basename(input)
        
    return {'path': path, 'height': src_h, 'width': src_w}

def rqst_photo(input):
    photo = {'url': 'null', 'height': 100, 'width': 100}
    current = 0
    for size in input['sizes']:
        if size['type'] == 'w':
            photo = {'url': size['url'], 'height': size['height'], 'width': size['width']}
            break
        elif size['type'] == 's' and current < 1:
            current = 1
            photo = {'url': size['url'], 'height': size['height'], 'width': size['width']}
        elif size['type'] == 'm' and current < 2:
            current = 2
            photo = {'url': size['url'], 'height': size['height'], 'width': size['width']}
        elif size['type'] == 'x' and current < 3:
            current = 3
            photo = {'url': size['url'], 'height': size['height'], 'width': size['width']}
        elif size['type'] == 'y' and current < 4:
            current = 4
            photo = {'url': size['url'], 'height': size['height'], 'width': size['width']}
        elif size['type'] == 'z' and current < 5:
            current = 5
            photo = {'url': size['url'], 'height': size['height'], 'width': size['width']}
    return photo

def rqst_message_service(input):
    url_link = '<a href="%s" style="color: #70777b">%s</a>'
    goto_link = '<a href="#go_to_message%d" onclick="return GoToMessage(%d)" title="%s" style="color: #70777b">%s</a>'
    from_id = rqst_user(input['from_id'])
    type = input['action']['type']
    
    from_prefix = 'https://vk.com/id' if from_id['id'] > 0 else 'https://vk.com/club'

    if type == 'chat_create':
        message = url_link % (from_prefix + str_to_plus(from_id['id']), from_id['name']) + f' создал беседу «{input["action"]["text"]}»'

    elif type == 'chat_title_update':
        message = url_link % (from_prefix + str_to_plus(from_id['id']), from_id['name']) + f' изменил название беседы на «{input["action"]["text"]}»'
 
    elif type == 'chat_invite_user_by_link':
        message = url_link % (from_prefix + str(from_id['id']), from_id['name']) + ' присоединился к беседе по ссылке'

    elif type == 'chat_photo_update':
        rqst_file(rqst_photo(input['attachments'][0]['photo'])['url'], f'userpics/up{input["conversation_message_id"]}.jpg')
        
        message = (
            f'{url_link % (from_prefix + str_to_plus(from_id["id"]), from_id["name"])} обновил фотографию беседы\n'
            f'<div class="userpic_wrap">'
            f'    <a class="userpic_link" href="userpics/up{input["conversation_message_id"]}.jpg">\n'
            f'        <img class="userpic" src="userpics/up{input["conversation_message_id"]}.jpg" style="width: 60px; height: 60px">'
            f'    </a>'
            f'</div>\n'
        )

    elif type == 'chat_photo_remove':
        message = (f'{url_link % (from_prefix + str_to_plus(from_id["id"]), from_id["name"])} удалил фотографию беседы\n')

    elif type == 'chat_pin_message' or type == 'chat_unpin_message':
        prefix = ' закрепил ' if type == 'chat_pin_message' else ' открепил '
        member_id = rqst_user(input['action']['member_id'])
        message = url_link % (from_prefix + str(member_id['id']), member_id['name']) + prefix
        
        if 'message' in input['action']:
            message += 'сообщение: ' + goto_link % (
                input['action']["conversation_message_id"], 
                input['action']["conversation_message_id"], 
                input['action']['message'],
                f'«{input["action"]["message"]}»')
        else:
            message += goto_link % (input['action']["conversation_message_id"], input['action']["conversation_message_id"], '', 'сообщение')

    elif type == 'chat_invite_user' or type == 'chat_kick_user':
        us_prefix = 'https://vk.com/id' if input['from_id'] > 0 else 'https://vk.com/club'
        us_postfix = 'https://vk.com/id' if input['action']['member_id'] > 0 else 'https://vk.com/club'

        if type == 'chat_invite_user':
            self_prefix = ' вернулся в беседу'
            other_prefix = ' пригласил '
        else:
            self_prefix = ' вышел из беседы'
            other_prefix = ' исключил '

        if input['from_id'] == input['action']['member_id']:
            message = url_link % (us_prefix + str_to_plus(from_id['id']), from_id['name']) + self_prefix
        else:
            passive = rqst_user(input['action']['member_id'])
            message = url_link % (us_prefix + str_to_plus(from_id['id']), from_id['name']) + other_prefix + url_link % (us_postfix + str_to_plus(passive['id']), passive['name'])
            
    else:
        log(2, f'missing_service: {input}')

    return f'\n<div class="message service" id="message{input["id"]}"><div class="body details">\n    {message}</div>\n</div>\n'

def rqst_attachments(input):
    joined_switch = False

    pre_attachments = post_attachments = ''

    data_blank = (
        '%s\n'
        '   <div class="fill pull_left"></div>\n'
        '   <div class="body">\n'
        '       <div class="title bold">%s</div>\n'
        '       <div class="status details">%s</div>\n'
        '   </div>'
        '</a>\n'
    )
    
    human_date = datetime.datetime.fromtimestamp(input['date']).strftime('%y-%m-%d_%H-%M-%S')

    if 'geo' in input:
        joined_switch = True
        html_details = f'{input["geo"]["coordinates"]["latitude"]}, {input["geo"]["coordinates"]["longitude"]}'
        if 'place' in input["geo"]:
            html_details = f'{input["geo"]["place"]["title"]} ({html_details})'

        pre_attachments = '<div class="media_wrap clearfix">\n%s</div>\n' % ( data_blank % ('<a class="media clearfix pull_left block_link media_location">', 'Местоположение', html_details) )
        
    for i in range(len(input['attachments'])):
        a = input['attachments'][i]
        data_fragment = 'missing_attachment = %s' % a
        json_fragment = f'title="{str_esc(json.dumps(a, indent=10, ensure_ascii=False, sort_keys=True))}"' if dump_json else ''

        if a['type'] == 'wall':
            href = f'https://vk.com/wall{a["wall"]["to_id"]}_{a["wall"]["id"]}'
            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_game" {json_fragment} href="{href}">', 
                                          'Запись', 
                                          href)

        if a['type'] == 'poll':
            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_game" {json_fragment} href="https://vk.com/poll{a["poll"]["owner_id"]}_{a["poll"]["id"]}">', 
                                          'Опрос', 
                                          f'id{a["poll"]["question"]}')

        if a['type'] == 'gift':
            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_game" {json_fragment} href="{a["gift"]["thumb_256"]}">', 
                                          'Подарок', 
                                          f'id{a["gift"]["id"]}')

        if a['type'] == 'link':
            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_game" {json_fragment} href="{a["link"]["url"]}">', 
                                          a['link']['title'], 
                                          a['link']['caption'] if 'caption' in a['link'] else '')

        if a['type'] == 'market':
            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_invoice" {json_fragment} href="https://vk.com/market{a["market"]["owner_id"]}_{a["market"]["id"]}">', 
                                          a['market']['title'], 
                                          a['market']['price']['text']) 

        if a['type'] == 'wall_reply':
            if 'deleted' in a['wall_reply']:
                html_title = 'Комментарий к записи (удалён)'
                href = ''
            else:
                html_title = 'Комментарий к записи'
                href = f'https://vk.com/wall{a["wall_reply"]["owner_id"]}_{a["wall_reply"]["post_id"]}?reply={a["wall_reply"]["id"]}'

            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_game" {json_fragment} href="{href}">', html_title, href)

        if a['type'] == 'doc':
            namefile = a['doc']['title']
            if namefile[-len(a['doc']['ext']):] == a['doc']['ext']:
                namefile = namefile[:-len(a['doc']['ext']) - 1]

            if dump_docs:
                href = f'docs/{str_fix(namefile)}-{i}-{input["conversation_message_id"]}_{human_date}.{a["doc"]["ext"]}'
                rqst_file(a['doc']['url'], href)
            else:
                href = a['doc']['url']

            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_file" {json_fragment} href="{href}">', 
                                          namefile + '.' + a['doc']['ext'], 
                                          sizeof_fmt(a['doc']['size']))

        if a['type'] == 'video':
            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_video" {json_fragment} href="https://vk.com/video{a["video"]["owner_id"]}_{a["video"]["id"]}">', 
                                          f'{a["video"]["title"]}', 
                                          f'{datetime.timedelta(seconds=int(a["video"]["duration"]))} | {a["video"]["owner_id"]}_{a["video"]["id"]}')

        if a['type'] == 'audio':
            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_audio_file" {json_fragment}>', 
                                          f'{a["audio"]["artist"]} - {a["audio"]["title"]}', 
                                          f'{datetime.timedelta(seconds=int(a["audio"]["duration"]))} | {a["audio"]["owner_id"]}_{a["audio"]["id"]} ')
        
        if a['type'] == 'call':
            html_title = 'Исходящий ' if input['from_id'] == a['call']['initiator_id'] else 'Входящий '
            html_title += 'звонок' if a['call']['video'] == False else 'видеозвонок'

            if a['call']['state'] == 'canceled_by_initiator':
                html_details = 'Отменён'
            if a['call']['state'] == 'canceled_by_receiver':
                html_details = 'Отклонён'
            if a['call']['state'] == 'reached':
                html_details = f'Завершен ({datetime.timedelta(seconds=int(a["call"]["duration"]))})'

            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_call" {json_fragment}>', html_title, html_details)

        if a['type'] == 'graffiti':
            height = a["graffiti"]["height"]
            width = a["graffiti"]["width"]

            if dump_graffiti:
                namefile = f'graffiti-{input["conversation_message_id"]}-{i}_{human_date}.jpg'

                rqst_file(a["graffiti"]['url'], 'photos/' + namefile)
                thumb = rqst_thumb('photos/' + namefile, 350, 300)
                data_fragment = (
                    f'<a class="photo_wrap clearfix pull_left" href="photos/{namefile}">\n'
                    f'<img class="photo" src="{thumb["path"]}" style="width: {thumb["width"]}px; height: {thumb["height"]}px"/></a>'
                )
            else:
                data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_photo" {json_fragment} href="{a["graffiti"]["url"]}">', 
                                              'Граффити', 
                                              f'{height}x{width}')

        if a['type'] == 'audio_message':
            if dump_audiomessages:
                href = f'voice_messages/audio-{i}-{input["conversation_message_id"]}_{human_date}.ogg'
                rqst_file(a['audio_message']['link_ogg'], href)
            else:
                href = a['audio_message']['link_ogg']

            data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_voice_message" {json_fragment} href="{href}">', 
                                          'Голосовое сообщение', 
                                          datetime.timedelta(seconds=int(a["audio_message"]["duration"])))

        if a['type'] == 'sticker':
            if dump_stickers:
                rqst_file(a['sticker']['images'][1]['url'], f'userpics/st{a["sticker"]["sticker_id"]}.jpg')
                data_fragment = (
                    f'<a class="sticker_wrap clearfix pull_left" href="userpics/st{a["sticker"]["sticker_id"]}.jpg">\n'
                    f'<img class="sticker" src="userpics/st{a["sticker"]["sticker_id"]}.jpg" style="width: 128px; height: 128px"/></a>'
                )
            else:
                data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_photo" {json_fragment} href="{a["sticker"]["images"][1]["url"]}">', 
                                              'Стикер', 
                                              f'id{a["sticker"]["sticker_id"]}')

        if a['type'] == 'photo':
            photo = rqst_photo(a['photo'])

            if dump_photos:
                photo_date = datetime.datetime.fromtimestamp(a['photo']['date']).strftime('%y-%m-%d_%H-%M-%S')
                namefile = f'ph-{input["conversation_message_id"]}-{i}_{photo_date}.jpg'
                
                rqst_file(photo['url'], 'photos/' + namefile)
                thumb = rqst_thumb('photos/' + namefile, 350, 280)
                data_fragment = (
                    f'<a class="photo_wrap clearfix pull_left" href="photos/{namefile}">\n'
                    f'<img class="photo" src="{thumb["path"]}" style="width: {thumb["width"]}px; height: {thumb["height"]}px"/></a>'
                )
            else:
                data_fragment = data_blank % (f'<a class="media clearfix pull_left block_link media_photo" {json_fragment} href="{photo["url"]}">', 
                                              'Фото',
                                              f'{photo["height"]}x{photo["width"]}')

        if data_fragment.startswith('missing_attachment'):
            log(2, f'missing_attachment: {a}')

        if joined_switch:
            post_attachments += (
                f'<div class="message default clearfix joined">\n'
                f'    <div class="body">{data_fragment}\n'
                f'    </div>\n'
                f'</div>\n'
            )
        else:
            pre_attachments = f'<div class="media_wrap clearfix">\n{data_fragment}</div>\n'
            joined_switch = True

    return (pre_attachments, post_attachments)

def rqst_message(input, forwarded=False):
    global prev_id, prev_date
    fwd_messages = ''
    from_id = rqst_user(input['from_id'])

    def_blank = (
        '<div class="message default clearfix" id="message%s">\n'
        '    <div class="pull_left userpic_wrap">\n'
        '        <div class="userpic" style="width: 42px; height: 42px">\n'
        '            <a class="userpic_link" href="userpics/id%s.jpg">\n'
        '                <img class="userpic" src="userpics/id%s.jpg" style="width: 42px; height: 42px" />\n'
        '            </a>\n'
        '        </div>\n'
        '    </div>\n'
        '    <div class="body">\n'
        '        <div class="pull_right date details">%s</div>\n'
        '        <div class="from_name">%s</div>\n'
        '%s'# fwd_messages
        '        <div class="text">\n%s\n</div>\n'
        '%s'# fwd_text_prefix
        '%s'# pre_attachments
        '    </div>\n'
        '</div>\n'
        '%s\n' # post_attachments
    )

    fwd_blank = (
        '<div class="pull_left forwarded userpic_wrap">\n'
        '    <!-- start-fwd-id=%s" -->\n'
        '    <div class="userpic" style="width: 42px; height: 42px">\n'
        '        <a class="userpic_link" href="userpics/id%s.jpg">\n'
        '            <img class="userpic" src="userpics/id%s.jpg" style="width: 42px; height: 42px" /></a>\n'
        '    </div>\n'
        '</div>\n'
        '<div class="forwarded body">\n'
        '    <div class="from_name">\n'
        '        %s<span class="details"> %s</span>\n'
        '    </div>\n'
        '%s' # reply_message, fwd_messages
        '    <div class="text">\n%s</div>\n'
        '%s%s' # fwd_text_prefix, pre_attachments
        '</div>\n'
        '%s' # post_attachments
        '<!-- end-fwd -->\n'
    )

    jnd_blank = (
        '<div class="message default clearfix joined" id="%s">\n'
        '    <!-- joined-id%s-id%s" -->\n'
        '    <div class="body">\n'
        '        <div class="pull_right date details">%s</div>\n'
        '    <!-- joined-name %s" -->\n'
        '%s' # reply_message, fwd_messages
        '        <div class="text">\n%s</div>\n' 
        '%s%s' # fwd_text_prefix, pre_attachments
        '    </div>\n'
        '</div>\n'
        '%s\n' # post_attachments
    )
    
    if from_id['id'] > 0:
        sender = f'<a href="https://vk.com/id{from_id["id"]}">{from_id["name"]}</a>'    
    else:
        sender = f'<a href="https://vk.com/club{str_to_plus(from_id["id"])}">{from_id["name"]}</a>'

    date = datetime.datetime.fromtimestamp(input['date']).strftime('%d/%m/%y %H:%M:%S')
    if 'update_time' in input:
        date = f'({datetime.datetime.fromtimestamp(input["update_time"]).strftime("%H:%M:%S")}) {date}' 
    
    if 'reply_message' in input:
        if 'conversation_message_id' in input['reply_message']:
            fwd_messages += rqst_message(input['reply_message'], True) 
        else:
            fwd_messages +=  f'<div title="{input["reply_message"]}" class="reply_to details">Нет id пересланного сообщения</div>\n' 

    if 'fwd_messages' in input:
        for i in input['fwd_messages']:
            fwd_messages += rqst_message(i, True)

    pre_attachments, post_attachments = rqst_attachments(input)

    if forwarded:
        blank = fwd_blank
    elif prev_id == from_id['id'] and input['date'] - prev_date < 120:
        blank = jnd_blank
    else:
        prev_date = input['date']
        prev_id = from_id['id']
        blank = def_blank

    return blank % (input["conversation_message_id"], 
                    from_id["id"], from_id["id"],
                    sender if forwarded else date, 
                    date if forwarded else sender, 
                    fwd_messages,
                    str_esc(input["text"], True),
                    '<div class="message default"></div>\n' if input["text"] != '' and forwarded and 'fwd_messages' not in input else '', 
                    pre_attachments, 
                    post_attachments)

def makehtml(filename, page, page_number, count, target, chat):
    global progress_left, offset_count
    for i in range(page_number):
        #empty check
        while True:
            chunk = rqst_method('messages.getHistory', {'peer_id': target, 'count': 200, 'extended': 1, 'offset': offset_count * 200})
            if len(chunk['items']) != 0 or offset_count < 0:
                break
            else:
                offset_count -= 1

        for msg in reversed(chunk['items']):
            progress = (progress_left + 1) / count
            if isinstance(progress, int): progress = float(progress)
            block = int(round(20 * progress))

            log(0, f'[{str_cut(str_fix(chat["title"]), 20)} ({target})] '
                f'[{"#" * block + "-" * (20 - block)}] '
                f'| {page + 1} / {count // ( 200 * page_number ) + 1} / {i + 1} '
                f'| {const_offset_count - offset_count} / {const_offset_count} '
                f'| {progress_left + 1} / {count} '
                f'| {fix_val(progress * 100, 2)}% '
                f'| {len(users)} )', '\r')

            if 'action' in msg:
                write(filename, rqst_message_service(msg))
            else:
                write(filename, rqst_message(msg))

            progress_left += 1
        offset_count -= 1

def makedump(target):   
    global progress_left, offset_count, const_offset_count, page_number

    mainfile = (
        '<!DOCTYPE html>\n'
        '<html>\n'
        '\n'
        '<head>\n'
        '    <meta charset="utf-8" />\n'
        '    <title>%s</title>\n'
        '    <meta content="width=device-width, initial-scale=1.0" name="viewport" />\n'
        '    <link href="style.css" rel="stylesheet" />\n'
        '    <script src="script.js" type="text/javascript"></script>\n'
        '</head>\n'
        '\n'
        '<body onload="CheckLocation();">\n'
        '    <div class="page_wrap">\n'
        '        <div class="page_header">\n'
        '            <div class="content">\n'
        '                <div class="text bold" title="%s">%s\n'
        '                    <div class="pull_right userpic_wrap">\n'
        '                        <div class="userpic" style="width: 25px; height: 25px">\n'
        '                            <a class="userpic_link" href="userpics/main.jpg">\n'
        '                                <img class="userpic" src="userpics/main.jpg" style="width: 25px; height: 25px" />\n'
        '                            </a>\n'
        '                        </div>\n'
        '                    </div>\n'
        '                </div>\n'
        '            </div>\n'
        '        </div>\n'
        '        <div class="page_body chat_page">\n'
        '            <div class="history">\n'
    )

    start_time = time.time()
    me = rqst_method('users.get')[0]

    if target > 2e9:
        deactivated = 'https://vk.com/images/deactivated_200.png'
        request = rqst_method('messages.getChat', {'chat_id': target - int(2e9), 'fields': 'photo_200'})
        chat = {'title': request['title'], 'photo': request['photo_200'] if 'photo_200' in request else deactivated}
        admin = rqst_user(request['admin_id'], False)
        info = (f'Название: {chat["title"]}\n'
                f'Сохранено в: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
                f'Сидящий: {me["first_name"]} {me["last_name"]} ({me["id"]})\n'
                f'Админ: {admin["name"]} ({admin["id"]})\n'
                f'Юзеров: {request["members_count"]}')
    else:
        request = rqst_user(target, False)
        chat = {'title': request['name'], 'photo': request['photo']}
        info = (f'Название: {chat["title"]}\n'
                f'Сохранено в: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
                f'Сидящий: {me["first_name"]} {me["last_name"]} ({me["id"]})')

    work_dir = '%s (%s)' % (str_cut(str_fix(chat["title"]), 40, ''), str(target))

    if not os.path.exists(work_dir):
        shutil.copytree('blank', work_dir)
    os.chdir(work_dir)

    if dump_audiomessages:
        os.makedirs('voice_messages', exist_ok=True)
    if dump_photos or dump_graffiti:
        os.makedirs('photos/thumbnails', exist_ok=True)
    if dump_docs:
        os.makedirs('docs', exist_ok=True)
    os.makedirs('userpics', exist_ok=True)

    rqst_file(chat['photo'], 'userpics/main.jpg')
    
    progress_left = 0
    count = rqst_method('messages.getHistory', {'peer_id': target, 'count': 0})['count']
    const_offset_count = offset_count = count // 200 + 1

    page_count = count // (200 * page_number) + 1
    
    for page in range(page_count):
        filename = f'messages{page + 1}.html'
        if os.path.exists(filename):
            os.remove(filename)
        write(filename, mainfile % ( str_esc(chat["title"]), info, str_esc(chat["title"]) ) )
        if page != 0:
            write(filename, f'\n<a class="pagination block_link" href="messages{page}.html">Предыдущая страница ( {page} / {page_count} )</a>\n')
        makehtml(filename, page, page_number, count, target, chat)
        if page + 1 != page_count:
            write(filename, f'\n<a class="pagination block_link" href="messages{page + 2}.html">Cледующая страница ( {page + 2} / {page_count} )</a>\n')
        write(filename, '\n            </div>\n        </div>\n    </div>\n</body>\n</html>')
    os.chdir('..')
    log(3, f'[{str_cut(str_fix(chat["title"]), 20)} ({target})] [finished in: {datetime.timedelta(seconds=int(fix_val(time.time() - start_time, 0)))}]')

if __name__ == "__main__":
    if len(sys.argv) > 1:
        conversations = []
        for i in range(1, len(sys.argv)):
            users = {}
            prev_id = 0
            prev_date = 0
            if sys.argv[i] == '-noall':
                dump_audiomessages = False 
                dump_photos = False 
                dump_graffiti = False
                dump_stickers = False
                dump_docs = False
            elif sys.argv[i] == '-noaudio':
                dump_audiomessages = False 
            elif sys.argv[i] == '-nophoto':
                dump_photos = False 
            elif sys.argv[i] == '-nograffiti':
                dump_graffiti = False 
            elif sys.argv[i] == '-nostickers':
                dump_stickers = False
            elif sys.argv[i] == '-nodoc':
                dump_docs = False
            elif sys.argv[i] == '-nojson':
                dump_json = False

            elif sys.argv[i][:+1] == '+':
                page_number = int(sys.argv[i][1:]) // 200 + 1
                page_number_raw = int(sys.argv[i][1:]) / 200
                if page_number != page_number_raw + 1:
                    log(2, 'page_number rounded ( %s → %s )' % (fix_val(page_number_raw, 2), page_number))

            elif ':' in sys.argv[i]:
                lp = sys.argv[i].split(':')
                vk = VkApi(lp[0], lp[1], app_id=2685278, config_filename='lsconfig.json')
                while True:
                    try:
                        vk.auth()
                        os.remove('lsconfig.json')
                        conversations = rqst_dialogs()
                        break
                    except AuthError as ex:
                        # %)
                        if str(ex).endswith('vk_api@python273.pw'):
                            log(2, f'unknown catched, retrying...   ')
                            time.sleep(10)
                        else:
                            log(1, 'autechre error: ' + str(ex))
                            sys.exit()

            elif len(sys.argv[i]) == 85:
                vk = VkApi(token=sys.argv[i])
                conversations = rqst_dialogs()

            elif sys.argv[i] == 'all':
                me = rqst_method('users.get')[0]
                me_dir = 'Диалоги %s (%s)' % (str_fix(me['first_name'] + ' ' + me['last_name']), me['id'])
                os.makedirs(me_dir, exist_ok=True)
                if not os.path.exists(f'{me_dir}/blank'):
                    shutil.copytree('blank', f'{me_dir}/blank')
                os.chdir(me_dir)
                start_time = time.time()

                for i in range(len(conversations)):
                    makedump(conversations[i])
                    users = {}
                    prev_id = 0
                    prev_date = 0       

                log(3, f'all saved in: {datetime.timedelta(seconds=int(fix_val(time.time() - start_time, 0)))}')
                shutil.rmtree('blank')
                sys.exit()

            elif sys.argv[i] == 'self':
                makedump(rqst_method('users.get')[0]['id'])

            elif sys.argv[i][:+1] == '@':
                makedump(2000000000 + int(sys.argv[i][1:]))

            else:
                work = 'null'

                if isinstance(work, int): 
                    work = abs(work)

                check_group = rqst_method('groups.getById', {'user_ids': sys.argv[i]})
                check_user = rqst_method('users.get', {'user_ids': sys.argv[i]})
                
                if check_group != None and -check_group[0]['id'] in conversations:
                    work = str_to_minus(check_group[0]['id'])
                if check_user != None and check_user[0]['id'] in conversations: 
                    work = str_to_plus(check_user[0]['id'])
                    
                if work == 'null':
                    log(1, f'{sys.argv[i]} is invalid')
                else:
                    makedump(int(work))
    else:
        log(1, 'nothing to do!')
