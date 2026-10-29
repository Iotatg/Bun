from .tokens import TokenType
from .lexer import Lexer
from . import ast
from . import types
from .errors import ParseError


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self._match_body_depth = 0

    def _peek(self, offset=0):
        index = self.pos + offset
        if index >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[index]

    def _prev_line(self):
        """Line of the most recently consumed token."""
        if self.pos == 0:
            return self._peek().line
        return self.tokens[self.pos - 1].line

    def _check(self, ttype):
        return self._peek().type == ttype

    def _advance(self):
        tok = self.tokens[self.pos]
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _match(self, *types):
        if self._peek().type in types:
            return self._advance()
        return None

    def _expect(self, ttype, message):
        if self._check(ttype):
            return self._advance()
        tok = self._peek()
        raise ParseError("%s, found %s" % (message, tok.type), tok.line, tok.col)

    def parse(self):
        statements = []
        while not self._check(TokenType.EOF):
            statements.append(self._statement())
        return ast.Program(statements)

    def _statement(self):
        t = self._peek().type
        if t == TokenType.IMPORT:
            return self._import_stmt()
        if t == TokenType.EXPORT:
            return self._exported_decl()
        if t == TokenType.LET:
            return self._var_decl(False)
        if t == TokenType.VAR:
            return self._var_decl(True)
        if t == TokenType.FN:
            return self._fn_decl()
        if t == TokenType.STRUCT:
            return self._struct_decl()
        if t == TokenType.ENUM:
            return self._enum_decl()
        if t == TokenType.IMPL:
            return self._impl_decl()
        if t == TokenType.PROTOCOL:
            return self._protocol_decl()
        if t == TokenType.AT:
            return self._decorated_decl()
        if t == TokenType.IF:
            return self._if_stmt()
        if t == TokenType.WHILE:
            return self._while_stmt()
        if t == TokenType.FOR:
            return self._for_stmt()
        if t == TokenType.ASSERT:
            return self._assert_stmt()
        if t == TokenType.DEL:
            return self._del_stmt()
        if t == TokenType.YIELD:
            return self._yield_stmt()
        if t == TokenType.RETURN:
            return self._return_stmt()
        if t == TokenType.TRY:
            return self._try_stmt()
        if t == TokenType.WITH:
            return self._with_stmt()
        if (t == TokenType.IDENT and self._peek().value == "scope"
                and self._peek(1).type == TokenType.LBRACE
                and self._peek(1).line == self._peek().line):
            # `scope` is a soft keyword: it only starts a scope statement
            # when a block follows it on the same line.
            return self._scope_stmt()
        if t == TokenType.IDENT and self._peek().value == "match":
            # `match` is a soft keyword: it only starts a match statement
            # when a subject and a block follow it.
            node = self._try_match_stmt()
            if node is not None:
                return node
        if t == TokenType.THROW:
            return self._throw_stmt()
        if t == TokenType.BREAK:
            kw = self._advance()
            return ast.BreakStmt(kw.line, kw.col)
        if t == TokenType.CONTINUE:
            kw = self._advance()
            return ast.ContinueStmt(kw.line, kw.col)
        return self._expr_stmt()

    def _var_decl(self, mutable):
        kw = self._advance()
        if self._check(TokenType.LBRACKET) or self._check(TokenType.STAR):
            targets = [self._unpack_binding()]
            while self._match(TokenType.COMMA):
                if self._check(TokenType.ASSIGN):
                    break
                targets.append(self._unpack_binding())
            self._expect(TokenType.ASSIGN, "expected '=' after variable name")
            value = self._expression()
            return ast.UnpackStmt(targets, value, mutable, kw.line, kw.col)
        name = self._binding_name()
        type_ann = self._opt_type()
        if self._check(TokenType.COMMA):
            targets = [ast.Identifier(name, kw.line, kw.col)]
            while self._match(TokenType.COMMA):
                if self._check(TokenType.ASSIGN):
                    break
                targets.append(self._unpack_binding())
            self._expect(TokenType.ASSIGN, "expected '=' after variable name")
            value = self._expression()
            return ast.UnpackStmt(targets, value, mutable, kw.line, kw.col)
        self._expect(TokenType.ASSIGN, "expected '=' after variable name")
        value = self._expression()
        return ast.LetStmt(name, value, mutable, kw.line, kw.col,
                           type_ann=type_ann)

    def _unpack_binding(self):
        """Parse one binding target of an unpacking pattern."""
        start = self._peek()
        if self._check(TokenType.STAR):
            self._advance()
            name = self._binding_name()
            return ast.UnpackTarget("star", [], name, start.line, start.col)
        if self._check(TokenType.LBRACKET):
            self._advance()
            targets = []
            if not self._check(TokenType.RBRACKET):
                targets.append(self._unpack_binding())
                while self._match(TokenType.COMMA):
                    if self._check(TokenType.RBRACKET):
                        break
                    targets.append(self._unpack_binding())
            self._expect(TokenType.RBRACKET,
                         "expected ']' after unpacking targets")
            return ast.UnpackTarget("list", targets, None, start.line,
                                    start.col)
        name = self._binding_name()
        return ast.Identifier(name, start.line, start.col)

    def _binding_name(self):
        """Read a binding name.

        `from` is only meaningful inside import statements, so - like Python -
        it stays usable as an ordinary variable name everywhere else.
        """
        tok = self._peek()
        if tok.type == TokenType.FROM:
            self._advance()
            return "from"
        return self._expect(TokenType.IDENT, "expected variable name").value

    def _struct_decl(self):
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected struct name")
        self._expect(TokenType.LBRACE, "expected '{' after struct name")
        fields = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            fields.append(self._struct_field())
            self._match(TokenType.COMMA)
        self._expect(TokenType.RBRACE, "expected '}' after struct fields")
        return ast.StructDecl(name.value, fields, kw.line, kw.col)

    def _struct_field(self):
        start = self._peek()
        mutable = True
        if self._match(TokenType.LET):
            mutable = False
        elif self._match(TokenType.VAR):
            mutable = True
        name = self._expect(TokenType.IDENT, "expected field name")
        type_ann = self._opt_type()
        default = None
        if self._match(TokenType.ASSIGN):
            default = self._expression()
        return ast.StructField(name.value, type_ann, mutable, default,
                               start.line, start.col)

    def _enum_decl(self):
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected enum name")
        self._expect(TokenType.LBRACE, "expected '{' after enum name")
        variants = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            variants.append(self._enum_variant())
            self._match(TokenType.COMMA)
        self._expect(TokenType.RBRACE, "expected '}' after enum variants")
        return ast.EnumDecl(name.value, variants, kw.line, kw.col)

    def _enum_variant(self):
        start = self._peek()
        name = self._expect(TokenType.IDENT, "expected a variant name")
        field_types = []
        if self._match(TokenType.LPAREN):
            if not self._check(TokenType.RPAREN):
                while True:
                    field_types.append(self._type_name())
                    if not self._match(TokenType.COMMA):
                        break
                    if self._check(TokenType.RPAREN):
                        break
            self._expect(TokenType.RPAREN,
                         "expected ')' after the fields of a variant")
        return ast.EnumVariant(name.value, field_types, start.line, start.col)

    def _impl_decl(self):
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected type name after 'impl'")
        self._expect(TokenType.LBRACE, "expected '{' after impl name")
        methods = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            if not self._check(TokenType.FN):
                raise ParseError("expected a method in an impl block",
                                 self._peek().line, self._peek().col)
            methods.append(self._fn_decl())
        self._expect(TokenType.RBRACE, "expected '}' after impl methods")
        return ast.ImplDecl(name.value, methods, kw.line, kw.col)

    def _fn_decl(self):
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected function name")
        type_params = self._type_params()
        self._expect(TokenType.LPAREN, "expected '(' after function name")
        params = self._param_list()
        return_type = None
        if self._match(TokenType.ARROW):
            return_type = self._type_name()
        body = self._block()
        return ast.FnDecl(name.value, params, body, kw.line, kw.col,
                          return_type=return_type, type_params=type_params)

    def _type_params(self):
        """Parse the type parameters of a function: `<T, U: Num>`.

        The list is empty when the name of the function is followed by
        anything else than a `<`.
        """
        if not self._check(TokenType.LT):
            return []
        self._advance()
        params = []
        while not self._check(TokenType.GT):
            tok = self._expect(TokenType.IDENT, "expected type parameter name")
            bound = None
            if self._match(TokenType.COLON):
                bound = self._expect(TokenType.IDENT,
                                     "expected bound of type parameter").value
            params.append(ast.TypeParam(tok.value, bound, tok.line, tok.col))
            if not self._match(TokenType.COMMA):
                break
        self._expect(TokenType.GT, "expected '>' after type parameters")
        return params

    def _protocol_decl(self):
        """Parse a protocol: a set of method signatures."""
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected protocol name")
        self._expect(TokenType.LBRACE, "expected '{' after protocol name")
        methods = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            if not self._check(TokenType.FN):
                raise ParseError("expected a method signature in a protocol block",
                                 self._peek().line, self._peek().col)
            methods.append(self._method_signature())
        self._expect(TokenType.RBRACE, "expected '}' after protocol methods")
        return ast.ProtocolDecl(name.value, methods, kw.line, kw.col)

    def _method_signature(self):
        """Parse the signature of a method: the name, the parameters and the
        return type, without a body."""
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected method name")
        self._expect(TokenType.LPAREN, "expected '(' after method name")
        params = self._param_list()
        return_type = None
        if self._match(TokenType.ARROW):
            return_type = self._type_name()
        if not params or params[0].name != "self":
            raise ParseError(
                "expected 'self' as the first parameter of a protocol method",
                kw.line, kw.col)
        return ast.FnDecl(name.value, params, ast.Block([], kw.line, kw.col),
                          kw.line, kw.col, return_type=return_type)

    def _decorated_decl(self):
        """Parse a function with decorators in front of it.

        The decorators are applied from the closest one to the function
        outwards, so the name that is written last is the one that is
        called first.  The function may be exported, and the ``export``
        may be written before the decorators or after them.
        """
        decorators = []
        while self._match(TokenType.AT):
            name = self._expect(TokenType.IDENT, "expected a decorator name")
            decorators.append(ast.Identifier(name.value, name.line, name.col))
        exported = False
        if self._match(TokenType.EXPORT):
            exported = True
        if not self._check(TokenType.FN):
            raise ParseError("expected 'fn' after a decorator",
                             self._peek().line, self._peek().col)
        node = self._fn_decl()
        node.decorators = decorators
        node.exported = exported
        return node

    def _param_list(self):
        """Parse a parameter list.

        Supports plain parameters, defaults, `*args`, `**kwargs` and a
        bare `*` that marks the following parameters keyword-only.
        """
        params = []
        keyword_only = False
        if not self._check(TokenType.RPAREN):
            while True:
                param = self._param(keyword_only)
                if param.param_kind == "kwonly_marker":
                    keyword_only = True
                else:
                    if param.param_kind == "vararg":
                        keyword_only = True
                    params.append(param)
                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RPAREN):
                    break
        self._expect(TokenType.RPAREN, "expected ')' after parameters")
        return params

    def _param(self, keyword_only):
        if self._check(TokenType.DOUBLE_STAR):
            tok = self._advance()
            name = self._expect(TokenType.IDENT,
                                "expected parameter name after '**'")
            return ast.Param(name.value, self._opt_type(), None, "kwarg",
                             tok.line, tok.col)
        if self._check(TokenType.STAR):
            tok = self._advance()
            if self._check(TokenType.IDENT):
                name = self._expect(TokenType.IDENT,
                                    "expected parameter name after '*'")
                return ast.Param(name.value, self._opt_type(), None, "vararg",
                                 tok.line, tok.col)
            # A bare '*' marks the parameters that follow as keyword-only.
            return ast.Param("", None, None, "kwonly_marker",
                             tok.line, tok.col)
        tok = self._expect(TokenType.IDENT, "expected parameter name")
        type_name = self._opt_type()
        default = None
        if self._match(TokenType.ASSIGN):
            default = self._expression()
        kind = "kwonly" if keyword_only else "positional"
        return ast.Param(tok.value, type_name, default, kind,
                         tok.line, tok.col)

    def _opt_type(self):
        if self._match(TokenType.COLON):
            return self._type_name()
        return None

    def _type_name(self):
        """Parse a type: a name, or a name with type arguments.

        A type argument is a plain type name or a type variable, so a
        type is written `list<T>` and never `list<list<T>>`.
        """
        if self._check(TokenType.FN):
            return self._advance().value
        name = self._expect(TokenType.IDENT, "expected type name").value
        if not self._check(TokenType.LT):
            return name
        self._advance()
        args = []
        while not self._check(TokenType.GT):
            args.append(self._type_argument())
            if not self._match(TokenType.COMMA):
                break
        self._expect(TokenType.GT, "expected '>' after type arguments")
        return name + "<" + ", ".join(args) + ">"

    def _type_argument(self):
        """Parse one type argument: a type name or a type variable."""
        return self._expect(TokenType.IDENT, "expected type argument").value

    def _import_stmt(self):
        kw = self._advance()
        self._expect(TokenType.LBRACE, "expected '{' after 'import'")
        names = []
        if not self._check(TokenType.RBRACE):
            names.append(self._expect(TokenType.IDENT, "expected imported name").value)
            while self._match(TokenType.COMMA):
                names.append(
                    self._expect(TokenType.IDENT, "expected imported name").value)
        self._expect(TokenType.RBRACE, "expected '}' after import names")
        self._expect(TokenType.FROM, "expected 'from' after import list")
        path = self._expect(TokenType.STRING, "expected module path string")
        return ast.ImportStmt(names, path.value, kw.line, kw.col)

    def _exported_decl(self):
        self._advance()
        t = self._peek().type
        if t == TokenType.FN:
            decl = self._fn_decl()
        elif t == TokenType.AT:
            decl = self._decorated_decl()
        elif t in (TokenType.LET, TokenType.VAR):
            decl = self._var_decl(t == TokenType.VAR)
        else:
            tok = self._peek()
            raise ParseError(
                "'export' must precede 'fn', 'let', or 'var'", tok.line, tok.col)
        decl.exported = True
        return decl

    def _if_stmt(self):
        kw = self._advance()
        condition = self._expression()
        then_branch = self._block()
        else_branch = None
        if self._match(TokenType.ELSE):
            if self._check(TokenType.IF):
                else_branch = self._if_stmt()
            else:
                else_branch = self._block()
        return ast.IfStmt(condition, then_branch, else_branch, kw.line, kw.col)

    def _while_stmt(self):
        kw = self._advance()
        condition = self._expression()
        body = self._block()
        orelse = self._loop_else()
        return ast.WhileStmt(condition, body, orelse, kw.line, kw.col)

    def _loop_else(self):
        """Parse the ``else`` of a loop, the block that runs when the loop
        ends without a ``break``."""
        if not self._check(TokenType.ELSE):
            return None
        self._advance()
        return self._block()

    def _for_stmt(self):
        kw = self._advance()
        targets = [self._expect(TokenType.IDENT,
                                "expected loop variable name").value]
        while self._match(TokenType.COMMA):
            targets.append(self._expect(TokenType.IDENT,
                                       "expected loop variable name").value)
        self._expect(TokenType.IN, "expected 'in' after loop variable")
        iterable = self._expression()
        body = self._block()
        orelse = self._loop_else()
        return ast.ForStmt(targets, iterable, body, orelse, kw.line, kw.col)

    def _assert_stmt(self):
        kw = self._advance()
        condition = self._expression()
        message = None
        if self._match(TokenType.COMMA):
            message = self._expression()
        return ast.AssertStmt(condition, message, kw.line, kw.col)

    def _yield_stmt(self):
        """Parse `yield value` and a `yield` without a value.

        The value is optional: a `yield` that stands alone gives null to
        the program.
        """
        kw = self._advance()
        value = None
        nxt = self._peek()
        if (nxt.line == kw.line
                and nxt.type not in (TokenType.RBRACE, TokenType.EOF)):
            value = self._expression()
        return ast.YieldStmt(value, kw.line, kw.col)

    def _yield_expr(self):
        """Parse `yield value` as an expression.

        The value of the expression is the value that the program sends
        back into the generator.
        """
        kw = self._advance()
        value = None
        nxt = self._peek()
        if (nxt.line == kw.line
                and nxt.type not in (TokenType.RBRACE, TokenType.EOF)):
            value = self._expression()
        return ast.YieldExpr(value, kw.line, kw.col)

    def _del_stmt(self):
        """Parse `del name` and `del container[key]`."""
        kw = self._advance()
        name = self._expect(TokenType.IDENT, "expected a name after 'del'")
        target = ast.Identifier(name.value, name.line, name.col)
        if self._check(TokenType.LBRACKET):
            self._advance()
            index = self._subscript()
            self._expect(TokenType.RBRACKET, "expected ']' after index")
            target = ast.Index(target, index, name.line, name.col)
        return ast.DelStmt(target, kw.line, kw.col)

    def _try_match_stmt(self):
        """Parse a ``match`` statement, or return ``None``.

        ``match`` is a soft keyword.  When the tokens after it are not a
        subject and a block, the name is used as an ordinary identifier.
        """
        save = self.pos
        kw = self._advance()
        try:
            subject = self._expression()
        except ParseError:
            self.pos = save
            return None
        if not self._check(TokenType.LBRACE):
            self.pos = save
            return None
        self._advance()
        cases = []
        while not self._check(TokenType.RBRACE):
            pattern = self._match_case_pattern()
            self._expect(TokenType.FAT_ARROW,
                         "expected '=>' after a match pattern")
            body = self._match_body()
            cases.append((pattern, body))
            self._match(TokenType.COMMA)
        self._expect(TokenType.RBRACE, "expected '}' after the match cases")
        return ast.MatchStmt(subject, cases, kw.line, kw.col)

    def _match_case_pattern(self):
        """Parse the pattern of one case.

        A case may name more than one pattern, and it may carry a guard.
        """
        pattern = self._match_pattern()
        if self._check(TokenType.COMMA):
            # A case may name more than one pattern.  The first one
            # that matches wins, so the comma before the '=>' joins
            # the alternatives of one case.
            alternatives = [pattern]
            while self._match(TokenType.COMMA):
                alternatives.append(self._match_pattern())
            pattern = ast.MatchPattern("or", items=alternatives,
                                        line=pattern.line, col=pattern.col)
        if self._check(TokenType.IF):
            # A guard is a condition that has to hold for the case to
            # match.  It sees the names the pattern binds.
            self._advance()
            pattern.guard = self._expression()
        return pattern

    def _try_match_expr(self):
        """Parse a ``match`` expression, or return ``None``.

        The match is a soft keyword, so the name is an ordinary
        identifier when no subject and a block follow it.  Every arm of
        the expression answers a value.
        """
        save = self.pos
        kw = self._advance()
        try:
            subject = self._expression()
        except ParseError:
            self.pos = save
            return None
        if not self._check(TokenType.LBRACE):
            self.pos = save
            return None
        self._advance()
        cases = []
        while not self._check(TokenType.RBRACE):
            pattern = self._match_case_pattern()
            self._expect(TokenType.FAT_ARROW,
                         "expected '=>' after a match pattern")
            if self._check(TokenType.LBRACE):
                tok = self._peek()
                raise ParseError("the arm of a match expression answers a "
                                 "value, not a block", tok.line, tok.col)
            body = self._match_arm_value()
            cases.append((pattern, body))
            self._match(TokenType.COMMA)
        self._expect(TokenType.RBRACE, "expected '}' after the match cases")
        return ast.MatchExpr(subject, cases, kw.line, kw.col)

    def _match_arm_value(self):
        """Parse the value of one arm of a match expression.

        An arm that answers a value may not swallow the sign of the
        pattern of the next arm, so the value is parsed again without the
        additive operators when the parse lands on the '=>' of a case.
        """
        start = self.pos
        value = self._expression()
        if self._check(TokenType.FAT_ARROW):
            self.pos = start
            value = self._comparison()
        return value

    def _match_body(self):
        """Parse the body of one match case.

        A block holds many statements; anything else is one statement.  A
        dict literal as a case body needs parentheses, because a ``{``
        after ``=>`` always starts a block.
        """
        if self._check(TokenType.LBRACE):
            return self._block()
        start = self.pos
        self._match_body_depth += 1
        try:
            body = self._statement()
        finally:
            self._match_body_depth -= 1
        if (isinstance(body, ast.ExprStmt)
                and isinstance(body.expr, (ast.Identifier, ast.Index))
                and self._check(TokenType.COMMA) and self._unpack_ahead()):
            # The comma belongs to an unpacking assignment and not to the
            # list of the cases, so the body is parsed again without the
            # restriction of the case.
            self.pos = start
            body = self._statement()
        return body

    def _unpack_ahead(self):
        """Report whether the tokens after a comma are an unpacking target.

        The comma after the first name of an unpacking assignment is
        followed by the other names and an ``=``.  The comma that
        separates the cases of a ``match`` is followed by a pattern.
        """
        offset = 1
        while True:
            tok = self._peek(offset)
            if tok.type != TokenType.IDENT:
                return False
            offset += 1
            nxt = self._peek(offset)
            if nxt.type == TokenType.COMMA:
                offset += 1
                continue
            return nxt.type == TokenType.ASSIGN

    def _match_pattern(self):
        tok = self._peek()
        if (tok.type == TokenType.IDENT
                and self._peek(1).type == TokenType.DOT):
            # A variant of an enum: `Color.Red`, with the fields of a
            # variant written in parentheses: `Shape.Circle(radius)`.
            return self._enum_variant_pattern()
        if tok.type == TokenType.IDENT:
            if self._peek(1).type == TokenType.LPAREN:
                # A pattern of a struct: `Point(x: 0, y)`. The value has
                # to be a struct of the named type, and the fields are
                # matched one by one.
                return self._struct_pattern()
            if tok.value == "_":
                self._advance()
                return ast.MatchPattern("wildcard", line=tok.line, col=tok.col)
            if tok.value in types.TYPE_NAMES:
                self._advance()
                return ast.MatchPattern("type", value=tok.value,
                                        line=tok.line, col=tok.col)
            self._advance()
            return ast.MatchPattern("binding", name=tok.value,
                                    line=tok.line, col=tok.col)
        if tok.type == TokenType.LBRACKET:
            self._advance()
            items = []
            tail = None
            if not self._check(TokenType.RBRACKET):
                while True:
                    if self._check(TokenType.STAR):
                        # A tail: the rest of the list, bound to a name.
                        self._advance()
                        name = self._expect(
                            TokenType.IDENT,
                            "expected a name after '*' in a match pattern")
                        tail = ast.MatchPattern("binding", name=name.value,
                                                line=name.line, col=name.col)
                    else:
                        items.append(self._match_pattern())
                    if not self._match(TokenType.COMMA):
                        break
                    if self._check(TokenType.RBRACKET):
                        break
                    if tail is not None:
                        raise ParseError("'*' must be the last item of a match "
                                         "pattern", tok.line, tok.col)
            self._expect(TokenType.RBRACKET, "expected ']' after a match pattern")
            return ast.MatchPattern("list", items=items, tail=tail,
                                    line=tok.line, col=tok.col)
        if tok.type == TokenType.LBRACE:
            self._advance()
            entries = []
            if not self._check(TokenType.RBRACE):
                key = self._expect(TokenType.STRING,
                                   "expected a string key in a match pattern")
                self._expect(TokenType.COLON,
                             "expected ':' after a match pattern key")
                entries.append((key.value, self._match_pattern()))
                while self._match(TokenType.COMMA):
                    if self._check(TokenType.RBRACE):
                        break
                    key = self._expect(TokenType.STRING,
                                       "expected a string key in a match pattern")
                    self._expect(TokenType.COLON,
                                 "expected ':' after a match pattern key")
                    entries.append((key.value, self._match_pattern()))
            self._expect(TokenType.RBRACE, "expected '}' after a match pattern")
            return ast.MatchPattern("dict", entries=entries, line=tok.line,
                                    col=tok.col)
        value = self._literal_pattern_value()
        if (self._check(TokenType.IDENT) and self._peek().value == "to"):
            self._advance()
            high_tok = self._peek()
            high = self._literal_pattern_value()
            return ast.MatchPattern("range", value=value, high=high,
                                    line=tok.line, col=tok.col)
        return ast.MatchPattern("literal", value=value, line=tok.line,
                                col=tok.col)

    def _enum_variant_pattern(self):
        """Parse the pattern of a variant of an enum.

        The pattern of `Color.Red` is the name of the enum, the name of
        the variant and no field, and the pattern of `Shape.Circle(r)`
        is the same with one field bound by position.
        """
        name_tok = self._advance()
        self._expect(TokenType.DOT, "expected '.' in a variant pattern")
        variant = self._expect(TokenType.IDENT, "expected a variant name")
        items = []
        if self._match(TokenType.LPAREN):
            if not self._check(TokenType.RPAREN):
                while True:
                    items.append(self._match_pattern())
                    if not self._match(TokenType.COMMA):
                        break
                    if self._check(TokenType.RPAREN):
                        break
            self._expect(TokenType.RPAREN,
                         "expected ')' after the fields of a variant")
        return ast.MatchPattern("enum", value=name_tok.value,
                                name=variant.value, items=items,
                                line=name_tok.line, col=name_tok.col)

    def _struct_pattern(self):
        """Parse the pattern of a struct.

        `Point(x: 0, y)` names the struct, tests the field `x` against
        the literal `0` and binds the field `y` to a name. A bare name
        is the pattern of the field that name holds, so `Point(x, y)`
        binds both fields.
        """
        name_tok = self._advance()
        self._expect(TokenType.LPAREN,
                     "expected '(' after the name of a struct pattern")
        entries = []
        if not self._check(TokenType.RPAREN):
            while True:
                field = self._expect(
                    TokenType.IDENT,
                    "expected a field name in a struct pattern")
                if self._match(TokenType.COLON):
                    sub = self._match_pattern()
                else:
                    sub = ast.MatchPattern("binding", name=field.value,
                                           line=field.line, col=field.col)
                entries.append((field.value, sub))
                if not self._match(TokenType.COMMA):
                    break
                if self._check(TokenType.RPAREN):
                    break
        self._expect(TokenType.RPAREN,
                     "expected ')' after the fields of a struct pattern")
        return ast.MatchPattern("struct", value=name_tok.value,
                                entries=entries,
                                line=name_tok.line, col=name_tok.col)

    def _literal_pattern_value(self):
        """Parse the value of a literal or range pattern."""
        tok = self._peek()
        if tok.type in (TokenType.INT, TokenType.FLOAT):
            self._advance()
            return tok.value
        if tok.type == TokenType.STRING:
            self._advance()
            return tok.value
        if tok.type == TokenType.TRUE:
            self._advance()
            return True
        if tok.type == TokenType.FALSE:
            self._advance()
            return False
        if tok.type == TokenType.NULL:
            self._advance()
            return None
        raise ParseError("expected a pattern, found %s" % tok.type,
                         tok.line, tok.col)

    def _return_stmt(self):
        kw = self._advance()
        value = None
        if (not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF)
                and self._peek().line == kw.line):
            value = self._expression()
        return ast.ReturnStmt(value, kw.line, kw.col)

    def _try_stmt(self):
        kw = self._advance()
        try_block = self._block()
        params = []
        catch_block = None
        if self._match(TokenType.CATCH):
            if self._match(TokenType.LPAREN):
                name = self._expect(TokenType.IDENT, "expected exception name")
                self._expect(TokenType.RPAREN, "expected ')' after exception name")
                params.append(name.value)
            elif self._check(TokenType.IDENT):
                params.append(self._advance().value)
            catch_block = self._block()
        finally_body = None
        if self._match(TokenType.FINALLY):
            finally_body = self._block()
        if catch_block is None and finally_body is None:
            tok = self._peek()
            raise ParseError(
                "expected 'catch' or 'finally' after 'try' block",
                tok.line, tok.col)
        return ast.TryStmt(try_block, params, catch_block, finally_body,
                           kw.line, kw.col)

    def _with_stmt(self):
        kw = self._advance()
        items = [self._with_item()]
        while self._match(TokenType.COMMA):
            items.append(self._with_item())
        body = self._block()
        return ast.WithStmt(items, body, kw.line, kw.col)

    def _scope_stmt(self):
        kw = self._advance()
        body = self._block()
        return ast.ScopeStmt(body, kw.line, kw.col)

    def _with_item(self):
        expr = self._expression()
        self._expect(TokenType.AS, "expected 'as' after 'with' expression")
        tok = self._peek()
        if tok.type == TokenType.IDENT:
            self._advance()
            name = tok.value
        elif tok.type == TokenType.AS:
            self._advance()
            name = "as"
        else:
            raise ParseError("expected variable name after 'as'",
                             tok.line, tok.col)
        return ast.WithItem(expr, name, expr.line, expr.col)

    def _throw_stmt(self):
        kw = self._advance()
        value = self._expression()
        cause = None
        if self._match(TokenType.COMMA):
            cause = self._expression()
        return ast.ThrowStmt(value, cause, kw.line, kw.col)

    def _expr_stmt(self):
        start = self._peek()
        if self._check(TokenType.INCREMENT) or self._check(TokenType.DECREMENT):
            return self._inc_dec_stmt(start, True)
        expr = self._statement_expression()
        if self._check(TokenType.COMMA) and self._match_body_depth == 0:
            targets = [self._unpack_target(expr)]
            while self._match(TokenType.COMMA):
                if self._check(TokenType.ASSIGN):
                    break
                targets.append(self._unpack_target(self._expression()))
            self._expect(TokenType.ASSIGN, "expected '=' in assignment")
            value = self._expression()
            target = ast.UnpackTarget("tuple", targets, None, start.line,
                                      start.col)
            return ast.AssignStmt(target, value, start.line, start.col)
        compound = self._compound_op()
        if compound is not None:
            value = self._expression()
            return ast.OpAssignStmt(self._assign_target(expr, start),
                                    compound, value, start.line, start.col)
        if self._match(TokenType.ASSIGN):
            value = self._expression()
            if isinstance(expr, ast.ListLiteral):
                targets = [self._unpack_target(element)
                           for element in expr.elements]
                target = ast.UnpackTarget("list", targets, None, start.line,
                                          start.col)
                return ast.AssignStmt(target, value, start.line, start.col)
            if not isinstance(expr, (ast.Identifier, ast.Index, ast.Attribute)):
                raise ParseError("invalid assignment target", start.line, start.col)
            return ast.AssignStmt(expr, value, start.line, start.col)
        if self._check(TokenType.INCREMENT) or self._check(TokenType.DECREMENT):
            if self._peek().line != self._prev_line():
                return ast.ExprStmt(expr, start.line, start.col)
            return self._inc_dec_stmt(start, False, expr)
        return ast.ExprStmt(expr, start.line, start.col)

    def _compound_op(self):
        """Read the operator of a compound assignment, if there is one."""
        table = {
            TokenType.PLUS_ASSIGN: "+",
            TokenType.MINUS_ASSIGN: "-",
            TokenType.STAR_ASSIGN: "*",
            TokenType.SLASH_ASSIGN: "/",
            TokenType.PERCENT_ASSIGN: "%",
            TokenType.AMP_ASSIGN: "&",
            TokenType.PIPE_ASSIGN: "|",
            TokenType.CARET_ASSIGN: "^",
            TokenType.LSHIFT_ASSIGN: "<<",
            TokenType.RSHIFT_ASSIGN: ">>",
        }
        tok = self._peek()
        if tok.type in table:
            self._advance()
            return table[tok.type]
        return None

    def _assign_target(self, expr, start):
        """Check that an expression may hold the result of an assignment."""
        if isinstance(expr, (ast.Identifier, ast.Index, ast.Attribute)):
            return expr
        raise ParseError("invalid assignment target", start.line, start.col)

    def _inc_dec_stmt(self, start, prefix, expr=None):
        """Parse the increment or the decrement of a name.

        The two signs are a statement and not an expression: a language
        that answers a value for `x++` keeps two rules for one name.
        """
        if prefix:
            op = self._advance()
            expr = self._postfix()
        else:
            op = self._advance()
        if not isinstance(expr, (ast.Identifier, ast.Index, ast.Attribute)):
            raise ParseError("invalid target for the increment",
                             start.line, start.col)
        sign = "+" if op.type == TokenType.INCREMENT else "-"
        return ast.IncDecStmt(expr, sign, start.line, start.col)

    def _unpack_target(self, expr):
        """Validate one target of an unpacking assignment."""
        if isinstance(expr, ast.UnpackTarget):
            return expr
        if isinstance(expr, (ast.Identifier, ast.Index)):
            return expr
        raise ParseError("invalid assignment target",
                         getattr(expr, "line", 0), getattr(expr, "col", 0))

    def _block(self):
        lbrace = self._expect(TokenType.LBRACE, "expected '{'")
        statements = []
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            statements.append(self._statement())
        self._expect(TokenType.RBRACE, "expected '}'")
        return ast.Block(statements, lbrace.line, lbrace.col)

    def _expression(self):
        expr = self._coalesce()
        if (self._check(TokenType.INCREMENT) or self._check(TokenType.DECREMENT)) \
                and self._peek().line == self._prev_line():
            tok = self._peek()
            raise ParseError("the increment is a statement, not an expression",
                             tok.line, tok.col)
        return expr

    def _statement_expression(self):
        """Parse the expression of a statement.

        The statement itself reads the increment that follows the
        expression, so the check of `_expression` does not run here.
        """
        return self._coalesce()

    def _coalesce(self):
        """Parse `a ?? b`.

        The operator of the null binds looser than the words `and` and
        `or`, and it binds to the right, so `a ?? b ?? c` is
        `a ?? (b ?? c)`.
        """
        expr = self._or()
        if self._check(TokenType.NULL_COALESCE):
            op = self._advance()
            return ast.Binary(expr, "??", self._coalesce(), op.line, op.col)
        return expr

    def _or(self):
        expr = self._and()
        while self._check(TokenType.OR):
            op = self._advance()
            expr = ast.Logical(expr, "or", self._and(), op.line, op.col)
        return expr

    def _and(self):
        expr = self._not_expr()
        while self._check(TokenType.AND):
            op = self._advance()
            expr = ast.Logical(expr, "and", self._not_expr(), op.line, op.col)
        return expr

    def _not_expr(self):
        # The word form of the negation. It sits between "and" and the
        # comparisons, as in Python, so "not a == b" is "not (a == b)".
        if self._check(TokenType.NOT):
            op = self._advance()
            return ast.Unary("!", self._not_expr(), op.line, op.col)
        return self._equality()

    def _equality(self):
        expr = self._comparison()
        while self._peek().type in (TokenType.EQ, TokenType.NEQ):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._comparison(), op.line, op.col)
        return expr

    def _comparison(self):
        expr = self._bit_or()
        while self._peek().type in (TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._bit_or(), op.line, op.col)
        return expr

    def _bit_or(self):
        expr = self._bit_xor()
        while self._peek().type == TokenType.PIPE:
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._bit_xor(), op.line, op.col)
        return expr

    def _bit_xor(self):
        expr = self._bit_and()
        while self._peek().type == TokenType.CARET:
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._bit_and(), op.line, op.col)
        return expr

    def _bit_and(self):
        expr = self._shift()
        while self._peek().type == TokenType.AMP:
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._shift(), op.line, op.col)
        return expr

    def _shift(self):
        expr = self._term()
        while self._peek().type in (TokenType.LSHIFT, TokenType.RSHIFT):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._term(), op.line, op.col)
        return expr

    def _term(self):
        expr = self._factor()
        while self._peek().type in (TokenType.PLUS, TokenType.MINUS):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._factor(), op.line, op.col)
        return expr

    def _factor(self):
        expr = self._unary()
        while self._peek().type in (TokenType.STAR, TokenType.SLASH, TokenType.PERCENT):
            op = self._advance()
            expr = ast.Binary(expr, op.value, self._unary(), op.line, op.col)
        return expr

    def _unary(self):
        if self._peek().type in (TokenType.MINUS, TokenType.BANG, TokenType.TILDE):
            op = self._advance()
            return ast.Unary(op.value, self._unary(), op.line, op.col)
        return self._power()

    def _power(self):
        """Parse `a ** b`.

        The operator binds tighter than the multiplication, and its right
        hand side may hold a unary sign, as in Python.  The right hand
        side is a whole term, so `2 ** 3 * 4` is `2 ** (3 * 4)`, which is
        what Python does.
        """
        expr = self._postfix()
        if self._peek().type == TokenType.DOUBLE_STAR:
            op = self._advance()
            return ast.Binary(expr, "**", self._factor(), op.line, op.col)
        return expr

    def _postfix(self):
        expr = self._primary()
        while True:
            if self._peek().line != self._prev_line():
                # A postfix continuation must stay on the line of the
                # expression it continues, otherwise a new statement would
                # silently be glued onto the previous one.
                break
            if self._check(TokenType.LPAREN):
                self._advance()
                args = []
                kwargs = []
                if not self._check(TokenType.RPAREN):
                    while True:
                        if (self._check(TokenType.IDENT)
                                and self._peek(1).type == TokenType.ASSIGN):
                            name = self._advance().value
                            self._advance()
                            kwargs.append((name, self._expression()))
                        else:
                            args.append(self._expression())
                        if not self._match(TokenType.COMMA):
                            break
                        if self._check(TokenType.RPAREN):
                            break
                self._expect(TokenType.RPAREN, "expected ')' after arguments")
                expr = ast.Call(expr, args, expr.line, expr.col, kwargs=kwargs)
            elif (self._check(TokenType.LBRACE)
                  and isinstance(expr, ast.Identifier)
                  and expr.name == "spawn"):
                # `spawn { ... }` is sugar for `spawn(fn() { ... })`.
                body = self._block()
                function = ast.FnDecl("", [], body, expr.line, expr.col)
                expr = ast.Call(expr, [function], expr.line, expr.col)
            elif self._check(TokenType.LBRACKET):
                self._advance()
                index = self._subscript()
                self._expect(TokenType.RBRACKET, "expected ']' after index")
                expr = ast.Index(expr, index, expr.line, expr.col)
            elif self._check(TokenType.DOT):
                self._advance()
                name = self._expect(TokenType.IDENT, "expected name after '.'")
                if self._check(TokenType.LPAREN):
                    self._advance()
                    args = []
                    if not self._check(TokenType.RPAREN):
                        args.append(self._expression())
                        while self._match(TokenType.COMMA):
                            args.append(self._expression())
                    self._expect(TokenType.RPAREN, "expected ')' after arguments")
                    expr = ast.MethodCall(expr, name.value, args, expr.line, expr.col)
                else:
                    expr = ast.Attribute(expr, name.value, expr.line, expr.col)
            elif self._check(TokenType.QUESTION):
                op = self._advance()
                expr = ast.Unwrap(expr, op.line, op.col)
            else:
                break
        return expr

    def _subscript(self):
        """Parse a subscript: either a plain index or a slice."""
        start = None
        if not self._check(TokenType.COLON):
            start = self._expression()
        if not self._check(TokenType.COLON):
            return start
        tok = self._advance()               # the ':' that starts the slice
        stop = None
        step = None
        if not self._check(TokenType.COLON) and not self._check(TokenType.RBRACKET):
            stop = self._expression()
        if self._match(TokenType.COLON):
            if not self._check(TokenType.RBRACKET):
                step = self._expression()
        return ast.Slice(start, stop, step, tok.line, tok.col)

    def _primary(self):
        tok = self._peek()
        if tok.type in (TokenType.INT, TokenType.FLOAT, TokenType.STRING):
            self._advance()
            return ast.Literal(tok.value, tok.line, tok.col)
        if tok.type == TokenType.FSTRING:
            self._advance()
            parts = self._fstring_parts(tok.value, tok.line, tok.col)
            return ast.FString(parts, tok.line, tok.col)
        if tok.type == TokenType.TRUE:
            self._advance()
            return ast.Literal(True, tok.line, tok.col)
        if tok.type == TokenType.FALSE:
            self._advance()
            return ast.Literal(False, tok.line, tok.col)
        if tok.type == TokenType.NULL:
            self._advance()
            return ast.Literal(None, tok.line, tok.col)
        if tok.type == TokenType.YIELD:
            return self._yield_expr()
        if tok.type == TokenType.IDENT:
            if tok.value == "match":
                # `match` is a soft keyword: it only starts a match
                # expression when a subject and a block follow it.
                node = self._try_match_expr()
                if node is not None:
                    return node
            self._advance()
            return ast.Identifier(tok.value, tok.line, tok.col)
        if tok.type == TokenType.FROM:
            # `from` is a soft keyword: usable as an ordinary identifier
            # outside of import statements, exactly like Python.
            self._advance()
            return ast.Identifier("from", tok.line, tok.col)
        if tok.type == TokenType.AS:
            # `as` is a soft keyword for the same reason.
            self._advance()
            return ast.Identifier("as", tok.line, tok.col)
        if tok.type == TokenType.FN:
            self._advance()
            self._expect(TokenType.LPAREN, "expected '(' after 'fn'")
            params = self._param_list()
            return_type = None
            if self._match(TokenType.ARROW):
                return_type = self._type_name()
            body = self._block()
            return ast.FnDecl("", params, body, tok.line, tok.col,
                              return_type=return_type)
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._expression()
            self._expect(TokenType.RPAREN, "expected ')' after expression")
            return expr
        if tok.type == TokenType.LBRACE:
            self._advance()
            if self._check(TokenType.RBRACE):
                self._advance()
                return ast.DictLiteral([], tok.line, tok.col)
            key = self._expression()
            self._expect(TokenType.COLON, "expected ':' after dict key")
            value = self._expression()
            if self._check(TokenType.FOR):
                clauses = self._comprehension_clauses()
                self._expect(TokenType.RBRACE, "expected '}' after comprehension")
                return ast.Comprehension(None, key, value, clauses, True,
                                        tok.line, tok.col)
            entries = [(key, value)]
            while self._match(TokenType.COMMA):
                if self._check(TokenType.RBRACE):
                    break
                key = self._expression()
                self._expect(TokenType.COLON, "expected ':' after dict key")
                value = self._expression()
                entries.append((key, value))
            self._expect(TokenType.RBRACE, "expected '}' after dict entries")
            return ast.DictLiteral(entries, tok.line, tok.col)
        if tok.type == TokenType.LBRACKET:
            self._advance()
            if self._check(TokenType.RBRACKET):
                self._advance()
                return ast.ListLiteral([], tok.line, tok.col)
            element = self._expression()
            if self._check(TokenType.FOR):
                clauses = self._comprehension_clauses()
                self._expect(TokenType.RBRACKET, "expected ']' after comprehension")
                return ast.Comprehension(element, None, None, clauses, False,
                                        tok.line, tok.col)
            elements = [element]
            while self._match(TokenType.COMMA):
                if self._check(TokenType.RBRACKET):
                    break
                elements.append(self._expression())
            self._expect(TokenType.RBRACKET, "expected ']' after list elements")
            return ast.ListLiteral(elements, tok.line, tok.col)
        raise ParseError("unexpected token %s" % tok.type, tok.line, tok.col)

    def _comprehension_clauses(self):
        """Parse one or more `for ... in ... [if ...]` comprehension clauses."""
        clauses = []
        while True:
            tok = self._expect(TokenType.FOR, "expected 'for' in comprehension")
            name = self._expect(TokenType.IDENT,
                                "expected loop variable name in comprehension")
            self._expect(TokenType.IN, "expected 'in' after loop variable")
            iterable = self._expression()
            condition = None
            if self._match(TokenType.IF):
                condition = self._expression()
            clauses.append(ast.ComprehensionClause(
                name.value, iterable, condition, tok.line, tok.col))
            if not self._check(TokenType.FOR):
                break
        return clauses

    # ------------------------------------------------------------------
    # f-strings
    # ------------------------------------------------------------------

    _FSTRING_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
                        "v": "\v", "0": "\0", '"': '"', "'": "'", "\\": "\\"}

    def _fstring_parts(self, raw, line, col):
        """Split the raw body of an f-string into literal and expression parts."""
        parts = []
        literal = []
        index = 0
        length = len(raw)
        while index < length:
            ch = raw[index]
            if ch == "{":
                if index + 1 < length and raw[index + 1] == "{":
                    literal.append("{")
                    index += 2
                    continue
                source, spec, conv, self_doc, display, end = \
                    self._scan_fstring_expr(raw, index, line, col)
                if literal:
                    parts.append(ast.FStringPart(
                        literal=self._unescape("".join(literal), line, col)))
                    literal = []
                expr = self._fstring_expression(source, line, col)
                parts.append(ast.FStringPart(
                    expr=expr, spec=spec, conv=conv,
                    source_text=display if self_doc else None))
                index = end
                continue
            if ch == "}":
                if index + 1 < length and raw[index + 1] == "}":
                    literal.append("}")
                    index += 2
                    continue
                raise ParseError("single '}' in f-string", line, col)
            literal.append(ch)
            index += 1
        if literal:
            parts.append(ast.FStringPart(
                literal=self._unescape("".join(literal), line, col)))
        return parts

    def _scan_fstring_expr(self, raw, start, line, col):
        """Find the closing brace of an interpolated expression.

        Returns (source, spec, conversion, self_documenting, display, end).
        """
        index = start + 1
        length = len(raw)
        depth = 0
        quote = None
        while index < length:
            ch = raw[index]
            if quote is not None:
                if ch == "\\":
                    index += 2
                    continue
                if ch == quote:
                    quote = None
                index += 1
                continue
            if ch == '"' or ch == "'":
                quote = ch
                index += 1
                continue
            if ch in "([{":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "}":
                if depth == 0:
                    break
                depth -= 1
            index += 1
        if index >= length:
            raise ParseError("unterminated expression in f-string", line, col)
        content = raw[start + 1:index]
        end = index + 1
        parts = self._split_fstring_content(content, line, col)
        return parts + (end,)

    def _split_fstring_content(self, content, line, col):
        """Split `{expr!conv:spec}` into its three parts."""
        colon = -1
        bang = -1
        depth = 0
        quote = None
        index = 0
        while index < len(content):
            ch = content[index]
            if quote is not None:
                if ch == "\\":
                    index += 2
                    continue
                if ch == quote:
                    quote = None
                index += 1
                continue
            if ch == '"' or ch == "'":
                quote = ch
                index += 1
                continue
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == ":" and depth == 0 and colon == -1:
                colon = index
            elif ch == "!" and depth == 0 and bang == -1:
                if index + 1 < len(content) and content[index + 1] == "=":
                    index += 2
                    continue
                bang = index
            index += 1

        spec = None
        head = content
        if colon != -1:
            spec = content[colon + 1:]
            head = content[:colon]
        conv = None
        source = head
        if bang != -1:
            conv = head[bang + 1:]
            source = head[:bang]
        if conv is not None and conv not in ("r", "s"):
            raise ParseError("invalid f-string conversion '%s'" % conv, line, col)

        self_doc = False
        display = None
        stripped = source.rstrip()
        if stripped.endswith("=") and len(stripped) >= 2:
            previous = stripped[-2]
            if previous not in "=<>!":
                self_doc = True
                equals = len(stripped) - 1
                source = stripped[:equals].rstrip()
                # The displayed text keeps the source verbatim, including
                # the '=' that marks the self-documenting form.
                display = head[:equals + 1]
        return source, spec, conv, self_doc, display

    def _fstring_expression(self, source, line, col):
        if source.strip() == "":
            raise ParseError("empty expression in f-string", line, col)
        try:
            return parse_expression(source)
        except ParseError as error:
            raise ParseError(
                "invalid expression in f-string: %s" % error.message, line, col)

    def _unescape(self, text, line, col):
        if "\\" not in text:
            return text
        out = []
        index = 0
        while index < len(text):
            ch = text[index]
            if ch == "\\":
                index += 1
                if index >= len(text):
                    raise ParseError("invalid escape in f-string", line, col)
                nxt = text[index]
                if nxt not in self._FSTRING_ESCAPES:
                    raise ParseError(
                        "invalid escape '\\%s' in f-string" % nxt, line, col)
                out.append(self._FSTRING_ESCAPES[nxt])
                index += 1
                continue
            out.append(ch)
            index += 1
        return "".join(out)


def parse(source):
    return Parser(Lexer(source).tokenize()).parse()


def parse_expression(source):
    return Parser(Lexer(source).tokenize())._expression()
