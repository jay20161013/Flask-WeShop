# -*- coding: utf-8 -*-
import functools
from flask import render_template, redirect, abort, request, session
from wechatpy import WeChatClient, WeChatOAuth, WeChatPay
from wechatpy import parse_message, create_reply
from wechatpy.crypto import WeChatCrypto
from wechatpy.exceptions import InvalidAppIdException
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.utils import check_signature
from weshop.utils import ezlogger
from configs.config import Config
from . import wechat
from .chatbot import bot_reply


logger = ezlogger.get_logger('wechat', use_stream=False)

wechat_client = WeChatClient(Config. WECHAT_APP_ID, Config.WECHAT_APP_SECRET)
wechat_oauth = WeChatOAuth(app_id=Config.WECHAT_APP_ID,
                           secret=Config.WECHAT_APP_SECRET,
                           scope='snsapi_userinfo',
                           redirect_uri='')
wechat_pay = WeChatPay(appid=Config.WECHAT_APP_ID,
                       api_key=Config.WEPAY_API_KEY,
                       mch_id=Config.WEPAY_MCH_ID,
                       mch_cert=Config.WEPAY_MCH_CERT_PATH,
                       mch_key=Config.WEPAY_MCH_KEY_PATH)

wechat_client.menu.create({
    "button": [
        {
            "type": "view",
            "name": "快速订水",
            "url": "http://www.rockbot.top/weshop/quickbuy"
        },
        {
            "type": "view",
            "name": "水站商城",
            "url": "http://www.qq.com"
        }
    ]
})


def wechat_oauth_decorator(method):
    """微信鉴权，获取用户open id、user info"""

    @functools.wraps(method)
    def warpper(*args, **kwargs):
        if 'user_info' in session:
            return method(*args, **kwargs)

        code = request.args.get('code', None)
        if code:
            try:
                logger.debug('get access tocken...')
                res = wechat_oauth.fetch_access_token(code)
                logger.debug('get user info...')
                user_info = wechat_oauth.get_user_info(code)
                logger.debug('code exit, get res: %s, user_info: %s' % (res, user_info))
            except Exception as e:
                logger.debug('%s' % e)
                # 这里需要处理请求里包含的 code 无效的情况
                abort(403)
            else:
                session['user_info'] = user_info
        else:
            wechat_oauth.redirect_uri = request.url
            logger.debug('code NOT exit redirect to %s', wechat_oauth.authorize_url)
            return redirect(wechat_oauth.authorize_url)

        return method(*args, **kwargs)
    return warpper


@wechat.route('/check', methods=['GET', 'POST'])
def wechat_check():
    """微信服务器校验专用"""

    logger.debug('request values: %s' % request.values)
    logger.debug("request method: %s" % request.method)
    logger.debug(request.args)
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    echo_str = request.args.get('echostr', '')
    encrypt_type = request.args.get('encrypt_type', '')
    msg_signature = request.args.get('msg_signature', '')

    logger.debug('signature: %s' % signature)
    logger.debug('timestamp: %s' % timestamp)
    logger.debug('nonce: %s' % nonce)
    logger.debug('echo_str: %s' % echo_str)
    logger.debug('encrypt_type: %s' % encrypt_type)
    logger.debug('msg_signature: %s' % msg_signature)

    try:
        check_signature(Config.WECHAT_TOKEN, signature, timestamp, nonce)
    except InvalidSignatureException:
        logger.debug("check_signature FAILED!!!")
        abort(403)

    if request.method == 'GET':
        return echo_str
    else:
        openid = request.args.get('openid')
        logger.debug('openid: %s' % openid)

        if openid is None:
            logger.warn('wechat check NOT found openid!')
            return render_template('403.html')

        # print('Raw message: \n%s' % request.data)
        msg = None
        crypto = WeChatCrypto(Config.WECHAT_TOKEN, Config.WECHAT_AES_KEY, Config.WECHAT_APP_ID)
        try:
            msg = crypto.decrypt_message(
                request.data,
                msg_signature,
                timestamp,
                nonce
            )
            # print('Decrypted message: \n%s' % msg)
        except (InvalidSignatureException, InvalidAppIdException):
            abort(403)
        msg = parse_message(msg)
        if msg.type == 'text':
            reply = create_reply(bot_reply(msg.content), msg)
            logger.debug('==msg.content: %s', msg.content)
        else:
            reply = create_reply('对不起，懵逼了，我该说啥？？？', msg)

            logger.debug("return wechat.")
        return crypto.encrypt_message(
            reply.render(),
            nonce,
            timestamp
        )

