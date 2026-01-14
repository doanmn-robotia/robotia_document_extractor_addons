from odoo.addons.web.controllers import home
from odoo import http


# class HomeController(home.Home):

#     @http.route(['/web', '/odoo', '/odoo/<path:subpath>', '/scoped_app/<path:subpath>'], type='http', auth="none", readonly=home.Home._web_client_readonly)
#     def web_client(self, s_action=None, **kw):
#         response = super().web_client(s_action, **kw)
#         return response